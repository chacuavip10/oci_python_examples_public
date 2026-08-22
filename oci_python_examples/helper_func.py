import logging
import os
import random
import string
import sys
import time

import oci
import requests

# Own logger instead of importing one from main.py — importing from the
# entry-point module creates a circular import (main -> helper_func -> main)
# and breaks when main.py is executed as a script. logging.basicConfig() in
# main.py configures the root logger, and this child logger automatically
# inherits that configuration via propagation, so no cross-import is needed.
logger = logging.getLogger(__name__)

FREE_SHAPES = ("VM.Standard.E2.1.Micro", "VM.Standard.A1.Flex")
TELEGRAM_API_URL = "https://api.telegram.org/bot{bot_api}/sendMessage"
REQUEST_TIMEOUT = 10  # seconds, for Telegram HTTP calls


def clear_scr():
    # for windows
    if os.name == "nt":
        os.system("cls")
    # for mac and linux(here, os.name is 'posix')
    else:
        os.system("clear")


def get_availability_domain(identity_client, compartment_id) -> list:
    list_availability_domains_response = oci.pagination.list_call_get_all_results(
        identity_client.list_availability_domains, compartment_id
    )
    if len(list_availability_domains_response.data) == 0:
        logger.critical("❌ No available availability domain was found in your region")
        raise RuntimeError("No available availability domain was found in your region")
    return list_availability_domains_response.data


def select_from_list(items, list_label, prompt_label):
    """Generic 'print list, ask for a valid 1-based index, allow [s] to re-list' helper.

    Fixes a class of bugs present in the original script where the selected
    item was computed *inside* the retry loop (using a stale/sentinel index),
    which could raise IndexError or silently accept out-of-range input.
    """
    print(f"\n{list_label}")
    for index, item in enumerate(items):
        print(f"\t[{index + 1}]. {item}")
    print()

    index_choice = None
    while index_choice is None:
        answer = input(
            f">>> Choose the {prompt_label} [number index] in the list to continue. "
            f"Press [s] to view the list again! "
        )
        if answer in ("s", "S"):
            print(f"\n{list_label}")
            for index, item in enumerate(items):
                print(f"\t[{index + 1}]. {item}")
            print()
            continue
        try:
            candidate = int(answer)
        except ValueError:
            print("❌ Must be a number")
            continue
        if 1 <= candidate <= len(items):
            index_choice = candidate
        else:
            print(f"❌ Must be between 1 and {len(items)}")

    # Zero based index
    return items[index_choice - 1]


def input_with_confirm_availability_domain(identity_client, compartment_id):
    list_of_availability_domain = get_availability_domain(
        identity_client=identity_client, compartment_id=compartment_id
    )

    print("\nList of available domain in your region:")
    for index, domain_name in enumerate(list_of_availability_domain):
        print(f"\t[{index + 1}]. {domain_name.name}")
    print()

    while True:
        print(
            'Go to https://cloud.oracle.com/compute/instances/create, choose "Always '
            'Free-eligible" Availability domain in the Placement tab and click Edit to '
            "view full name."
        )
        print(
            '\n>>> Verify if "Always Free-eligible" Availability domain is listed above. '
            "If not, press [N]."
        )
        answer = input(">>> Confirm / Acknowledge [Y]es/[N]o: ")
        if answer in ("y", "Y"):
            break
        logger.error(
            'User not accept the confirmation or no available "Always Free-eligible" '
            "Availability domain. Script terminate automatically."
        )
        sys.exit()

    availability_domain = select_from_list(
        [d.name for d in list_of_availability_domain],
        "List of available domain in your region:",
        "Always Free-eligible Availability domain",
    )
    # Map name back to the original object
    availability_domain = next(
        d for d in list_of_availability_domain if d.name == availability_domain
    )
    logger.info(
        f'👉 "Always Free-eligible" Availability Domain setting by user: '
        f"{availability_domain.name}"
    )
    return availability_domain


def input_with_confirm_free_shape_to_add(
    compute_client, compartment_id, availability_domain
):
    free_shapes = get_free_shape(
        compute_client=compute_client,
        compartment_id=compartment_id,
        availability_domain=availability_domain,
    )
    print("\nNote: At the time of 2026-08-22:")
    print(
        "\t- VM.Standard.A1.Flex is LIMITED_FREE, with total of 2 instances and 2 cpu - 12 GB Memory per account"
    )
    print(
        "\t- VM.Standard.E2.1.Micro is ALWAYS_FREE, with total of 2 instances per account"
    )
    print(
        "\t- Recheck at https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm to get last update"
    )

    shape_name = select_from_list(
        [shape.shape for shape in free_shapes],
        "List of free shape in your domain:",
        "shape",
    )
    return next(shape for shape in free_shapes if shape.shape == shape_name)


def input_with_config_image_to_add(compute_client, compartment_id, shape_to_add, os):
    all_images = get_image_for_shape(
        compute=compute_client,
        compartment_id=compartment_id,
        shape=shape_to_add,
        operating_system=os,
    )
    image_name = select_from_list(
        [image.display_name for image in all_images],
        "List of image compatible with your instance:",
        "image",
    )
    return next(image for image in all_images if image.display_name == image_name)


def list_all_instances(compute_client, config):
    results = oci.pagination.list_call_get_all_results(
        compute_client.list_instances, compartment_id=config["tenancy"]
    ).data

    if not results:
        return None
    return results


def get_vcn(network_client, compartment_id) -> list:
    list_vcns_response = oci.pagination.list_call_get_all_results(
        network_client.list_vcns, compartment_id, lifecycle_state="AVAILABLE"
    )
    vcns = list_vcns_response.data
    if len(vcns) == 0:
        print(
            """Go to https://cloud.oracle.com/compute/instances/create, create 1 random free instance to make sure oci auto create 1 VCN/subnet for you.
You can ignore the out of capacity error.
Verify the newly create Network and subnet in [OCI Accout Web Console] Networking > Virtual Cloud Network.
"""
        )
        logger.critical("❌ No available network was found. Please create manually")
        raise RuntimeError("No available network was found. Please create manually")

    return vcns


def get_subnet(network_client, compartment_id) -> list:
    list_subnets_response = oci.pagination.list_call_get_all_results(
        network_client.list_subnets, compartment_id, lifecycle_state="AVAILABLE"
    )
    subnets = list_subnets_response.data
    if len(subnets) == 0:
        print(
            """Go to https://cloud.oracle.com/compute/instances/create, create 1 random free instance to make sure oci auto create 1 VCN/subnet for you.
You can ignore the out of capacity error.
Verify the newly create Network and subnet in [OCI Accout Web Console] Networking > Virtual Cloud Network.
"""
        )
        logger.critical("❌ No available subnet was found. Please create manually")
        raise RuntimeError("No available subnet was found. Please create manually")

    return subnets


def get_boot_volume(storage_client, availability_domain, compartment_id) -> list:
    list_volumes_response = oci.pagination.list_call_get_all_results(
        storage_client.list_boot_volumes,
        availability_domain=availability_domain,
        compartment_id=compartment_id,
    )
    return list_volumes_response.data


def get_block_volume(storage_client, compartment_id) -> list:
    list_volumes_response = oci.pagination.list_call_get_all_results(
        storage_client.list_volumes, compartment_id=compartment_id
    )
    return list_volumes_response.data


def free_tier_check(
    identity_client,
    compute_client,
    network_client,
    storage_client,
    config,
    future_to_add_number_of_E2_1_Micro=0,
    future_to_add_number_of_a1_flex_instance=0,
    future_to_add_a1_flex_ocpus=0.0,
    future_to_add_a1_flex_memory=0.0,
):
    logger.info("Check resources including the instance you try to create if any...")
    # Max 2 x VM.Standard.A1.Flex (2 ocpus/12GB), 2 x VM.Standard.E2.1.Micro
    free_exceed = False
    can_continue = True
    _a1_flex = _e2_1_micro = other_instances = 0
    _a1_flex_ocpus = _a1_flex_memory = 0
    instances_response = list_all_instances(
        compute_client=compute_client, config=config
    )

    if not instances_response:
        logger.info("✅ No compute instance (VM) found.")
    else:
        logger.info(f"{len(instances_response)} instances found!")
        logger.info(
            "⚠️  If instance in TERMINATING or TERMINATED state, script still count toward Free Tier resource. Please wait a day or two for OCI to clear."
        )
        for instance in instances_response:
            if instance.shape == "VM.Standard.E2.1.Micro":
                _e2_1_micro += 1
                logger.info(
                    f"\t🖳 {instance.display_name: <20} | {instance.shape: <24} | {instance.lifecycle_state: <16} | 1 ocpu - 1GB RAM        |"
                )
            elif instance.shape == "VM.Standard.A1.Flex":
                _a1_flex += 1
                _a1_flex_ocpus += float(instance.shape_config.ocpus)
                _a1_flex_memory += float(instance.shape_config.memory_in_gbs)
                logger.info(
                    f"\t🖳 {instance.display_name: <20} | {instance.shape: <24} | {instance.lifecycle_state: <16} | {instance.shape_config.ocpus} ocpus - {instance.shape_config.memory_in_gbs} GB RAM |"
                )
            else:
                other_instances += 1
                logger.info(
                    f"\t🖳 {instance.display_name: <20} | {instance.shape: <30} | {instance.lifecycle_state: <16} |"
                )

        if _a1_flex + future_to_add_number_of_a1_flex_instance > 2:
            free_exceed = True
            logger.warning(
                f"❌ VM.Standard.A1.Flex instances: Current {_a1_flex + future_to_add_number_of_a1_flex_instance} | Maximum: 4"
            )
        else:
            logger.info(
                f"✅ VM.Standard.A1.Flex instances: Current {_a1_flex + future_to_add_number_of_a1_flex_instance} | Maximum: 4"
            )

        if (
            _a1_flex_ocpus + future_to_add_a1_flex_ocpus > 2.0
            or _a1_flex_memory + future_to_add_a1_flex_memory > 12.0
        ):
            free_exceed = True
            logger.warning(
                f"❌ VM.Standard.A1.Flex resources: Current {_a1_flex_ocpus + future_to_add_a1_flex_ocpus} ocpus - {_a1_flex_memory + future_to_add_a1_flex_memory} GB Ram | Maximum: 2 ocpus - 12 GB Ram"
            )
        else:
            logger.info(
                f"✅ VM.Standard.A1.Flex resources: Current {_a1_flex_ocpus + future_to_add_a1_flex_ocpus} ocpus - {_a1_flex_memory + future_to_add_a1_flex_memory} GB Ram | Maximum: 2 ocpus - 12 GB Ram"
            )

        if _e2_1_micro + future_to_add_number_of_E2_1_Micro > 2:
            free_exceed = True
            logger.warning(
                f"❌ VM.Standard.E2.1.Micro instances: Current {_e2_1_micro + future_to_add_number_of_E2_1_Micro} | Maximum: 2"
            )
        else:
            logger.info(
                f"✅ VM.Standard.E2.1.Micro instances: Current {_e2_1_micro + future_to_add_number_of_E2_1_Micro} | Maximum: 2"
            )

        if other_instances > 0:
            free_exceed = True
            logger.warning(
                "❌ You have instance(s) shape not in Always Free-eligible program!"
            )

    # Checking VCN & Subnet
    try:
        vcns = get_vcn(network_client=network_client, compartment_id=config["tenancy"])
        if len(vcns) > 2:
            free_exceed = True
            logger.warning(
                f"❌ Virtual Cloud Network: Current {len(vcns)} | Maximum: 2"
            )
        else:
            logger.info(f"✅ Virtual Cloud Network: Current {len(vcns)} | Maximum: 2")
            for vcn in vcns:
                logger.info(
                    f"\t☁️ VCN Name: {vcn.display_name} | IP Block: {vcn.cidr_block}"
                )
    except RuntimeError:
        can_continue = False
        logger.warning(
            "❌ No available Virtual Cloud Network was found. Please create manually"
        )

    try:
        subnets = get_subnet(
            network_client=network_client, compartment_id=config["tenancy"]
        )
        if len(subnets) > 0:
            logger.info(
                f"✅ At least 1 subnet found. Current {len(subnets)} | Maximum: N/A"
            )
            for subnet in subnets:
                logger.info(
                    f"\t🖧  Subnet Name: {subnet.display_name} | IP Block: {subnet.cidr_block}"
                )
    except RuntimeError:
        can_continue = False
        logger.warning(
            "❌ No available Virtual Cloud Network was found. Please create manually"
        )

    # Check storage
    print_storage = []
    boot_volumes_GBs_total = block_volumes_GBs_total = 0.0

    list_avai_domains = get_availability_domain(
        identity_client, compartment_id=config["tenancy"]
    )
    if list_avai_domains:
        for domain in list_avai_domains:
            boot_volume_response = get_boot_volume(
                storage_client=storage_client,
                availability_domain=domain,
                compartment_id=config["tenancy"],
            )
            for volume in boot_volume_response:
                print_storage.append(
                    f"\t💽 Name: {volume.display_name} | Size: {volume.size_in_gbs} GBs"
                )
                boot_volumes_GBs_total += float(volume.size_in_gbs)

    block_volumes_response = get_block_volume(
        storage_client=storage_client, compartment_id=config["tenancy"]
    )
    for volume in block_volumes_response:
        print_storage.append(
            f"\t💽 Name: {volume.display_name} | Size: {volume.size_in_gbs} GBs"
        )
        block_volumes_GBs_total += float(volume.size_in_gbs)

    if boot_volumes_GBs_total + block_volumes_GBs_total > 200:
        free_exceed = True
        logger.warning(
            f"❌ Storage Size (Boot + Block Volumes): Current {boot_volumes_GBs_total + block_volumes_GBs_total} GBs | Maximum: 200 GBs"
        )
    else:
        logger.info(
            f"✅ Storage Size (Boot + Block Volumes): Current {boot_volumes_GBs_total + block_volumes_GBs_total} GBs | Maximum: 200 GBs"
        )
    for message in print_storage:
        logger.info(message)

    if free_exceed:
        logger.error("❌ Account exceed Free Tier resource limit!")
    elif not can_continue:
        logger.warning("Need manual step from user. Check log to proceed!")
    else:
        logger.info("✅ Account within Free Tier resource limit. Continue!")

    return (not free_exceed) and can_continue


# Helper for create instance
def get_shape(compute_client, compartment_id, availability_domain) -> list:
    list_shapes_response = oci.pagination.list_call_get_all_results(
        compute_client.list_shapes,
        compartment_id,
        availability_domain=availability_domain.name,
    )
    shapes = list_shapes_response.data
    if len(shapes) == 0:
        raise RuntimeError("No available shape was found.")

    vm_shapes = [shape for shape in shapes if shape.shape.startswith("VM")]
    if len(vm_shapes) == 0:
        raise RuntimeError("No available VM shape was found.")

    return vm_shapes


def get_free_shape(compute_client, compartment_id, availability_domain) -> list:
    """Return only shapes that are both free-tier eligible AND in FREE_SHAPES.

    NOTE: the original implementation had
        shape.shape in ["VM.Standard.E2.1.Micro"], ["VM.Standard.A1.Flex"]
    which builds a (bool, list) tuple that is always truthy, so the shape-name
    filter never actually applied. Fixed below.
    """
    vm_shapes = get_shape(compute_client, compartment_id, availability_domain)

    free_shape = [
        shape
        for shape in vm_shapes
        if shape.billing_type in ("ALWAYS_FREE", "LIMITED_FREE")
        and shape.shape in FREE_SHAPES
    ]
    return free_shape


def choose_os():
    os_options = {
        1: "Oracle Linux Cloud Developer",
        2: "Oracle Linux",
        3: "Oracle Autonomous Linux",
        4: "CentOS",
        5: "Canonical Ubuntu",
    }
    print("\nChoosing os for instance!")
    for key, value in os_options.items():
        print(f"[{key}]. {value}")

    answer = None
    while answer not in os_options:
        try:
            answer = int(input(">>> Choose the os for instances [1 2 3 4 5]: "))
        except ValueError:
            print("❌ Must be a number")
            answer = None

    return os_options[answer]


def get_image_for_shape(compute, compartment_id, shape, operating_system) -> list:
    # Operating system
    # - "Oracle Linux Cloud Developer"
    # - "Oracle Linux"
    # - "Oracle Autonomous Linux"
    # - "CentOS"
    # - "Canonical Ubuntu"
    list_images_response = oci.pagination.list_call_get_all_results(
        compute.list_images,
        compartment_id,
        operating_system=operating_system,
        shape=shape.shape,
        lifecycle_state="AVAILABLE",
    )
    images = list_images_response.data
    if len(images) == 0:
        raise RuntimeError("No available image was found.")

    return images


def telegram_setting(session):
    bot_api = None
    chat_id = None
    answer = input("\n>>> Do you want to sent notification via Telegram? [Y]es/[N]o: ")

    if answer not in ("y", "Y"):
        return bot_api, chat_id

    telegram_answer = None
    while telegram_answer not in ("y", "Y"):
        bot_api = input(">>> Bot API key: ")
        chat_id = input(">>> chat_id: ")
        test_message = "[TEST] Hello from oci script!"
        try:
            session.get(
                TELEGRAM_API_URL.format(bot_api=bot_api),
                params={"chat_id": chat_id, "text": test_message},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            print(f"❌ Failed to reach Telegram API: {e}")

        telegram_answer = input(
            ">>> Did you get the test message? Press [y] if received or any key to reconfig the api key/chat id >>> "
        )

    logger.info("👉 Telegram notification is enabled")
    return bot_api, chat_id


def telegram_notify(session, bot_api, chat_id, message):
    """Notify via telegram"""
    if not bot_api or not chat_id:
        return
    try:
        session.get(
            TELEGRAM_API_URL.format(bot_api=bot_api),
            params={"chat_id": chat_id, "text": message},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        logger.info("Message fail to sent via telegram")


def gen_random_instance_name():
    suffix = "".join(random.SystemRandom().choices(string.digits, k=10))
    return f"instance-{suffix}"


def gen_ssh_keygen():
    ssh_key = ""
    import subprocess
    from pathlib import Path

    ssh_pub_key = Path(".") / "script_ssh_key_autogen.pub"
    ssh_priv_key = Path(".") / "script_ssh_key_autogen"

    if ssh_pub_key.exists() and ssh_priv_key.exists():
        logger.info(f"SSH key found. {ssh_priv_key!s}")
    else:
        logger.info(
            "Create new ssh key pair, you can use this to login to your newly created instance."
        )
        logger.info("Feature are still in testing. Please also provide your ssh-key.")
        try:
            subprocess.run(
                [
                    "ssh-keygen",
                    "-b",
                    "2048",
                    "-t",
                    "rsa",
                    "-f",
                    "script_ssh_key_autogen",
                    "-q",
                    "-N",
                    "",
                ],
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.warning("❌ Fail to create ssh-key-pair using ssh-keygen")

    try:
        with open(ssh_pub_key, "r") as f:
            ssh_key = f.read().strip()
        logger.info(f"Script generated ssh-key: {ssh_key}")
        logger.info(
            "📌 Login usage: ssh -i script_ssh_key_autogen user@ip. Passphrase will be <empty passphrase>"
        )
    except OSError:
        pass
    return ssh_key


def input_user_ssh_key():
    answer = None
    user_ssh_key = ""
    while answer not in ("y", "Y", "n", "N"):
        print(
            "\nDo you want to add custom ssh-key to your instance. Note that instance only allow to login via key authentication."
        )
        print("Script also generate a key for you in current folder.")
        answer = input("Enter your choice [Y]es/[N]o: ")
        if answer in ("y", "Y"):
            user_ssh_key = input("Paste your ssh-key here >>> ")
            logger.debug("👉 User input custom ssh-key (redacted from log)")
        elif answer in ("n", "N"):
            logger.info("User not input ssh-key. Only using default key.")
    return user_ssh_key


def input_interval_between_request():
    logger.warning(
        "⚠️  Don't set the interval in second too low (DOS attack, may getting ban), recommend 300s (5 min)"
    )
    interval_between_requests = 0
    while interval_between_requests < 30:
        try:
            answer = input(
                "\n>>> Choose the time to wait between send request (default 300s). Enter to choose default: "
            )
            if answer == "":
                interval_between_requests = 300
            else:
                interval_between_requests = int(answer)
        except ValueError:
            print("❌ Must be a number")
    return interval_between_requests


def build_launch_instance_details(
    *,
    availability_domain,
    compartment_id,
    shape,
    display_name,
    image_id,
    subnet_id,
    ssh_authorized_keys,
    assign_public_ip,
    shape_config=None,
):
    """Build a LaunchInstanceDetails object.

    Factored out so VM.Standard.A1.Flex and VM.Standard.E2.1.Micro launch
    paths (previously ~90 lines of near-identical code each) share one
    implementation.
    """
    kwargs = {
        "metadata": {"ssh_authorized_keys": ssh_authorized_keys},
        "availability_domain": availability_domain,
        "shape": shape,
        "compartment_id": compartment_id,
        "display_name": display_name,
        "source_details": oci.core.models.InstanceSourceViaImageDetails(
            source_type="image", image_id=image_id
        ),
        "create_vnic_details": oci.core.models.CreateVnicDetails(
            assign_public_ip=assign_public_ip,
            subnet_id=subnet_id,
            assign_private_dns_record=True,
        ),
        "agent_config": oci.core.models.LaunchInstanceAgentConfigDetails(
            is_monitoring_disabled=False,
            is_management_disabled=False,
            plugins_config=[
                oci.core.models.InstanceAgentPluginConfigDetails(
                    name="Vulnerability Scanning", desired_state="DISABLED"
                ),
                oci.core.models.InstanceAgentPluginConfigDetails(
                    name="Compute Instance Monitoring", desired_state="DISABLED"
                ),
                oci.core.models.InstanceAgentPluginConfigDetails(
                    name="Bastion", desired_state="DISABLED"
                ),
            ],
        ),
        "defined_tags": {},
        "freeform_tags": {},
        "instance_options": oci.core.models.InstanceOptions(
            are_legacy_imds_endpoints_disabled=False
        ),
        "availability_config": oci.core.models.LaunchInstanceAvailabilityConfigDetails(
            recovery_action="RESTORE_INSTANCE"
        ),
    }
    if shape_config is not None:
        kwargs["shape_config"] = shape_config

    return oci.core.models.LaunchInstanceDetails(**kwargs)


def launch_instance_with_retry(
    compute_client,
    instance_details,
    interval_between_requests,
    session,
    bot_api,
    chat_id,
    success_message,
):
    """Repeatedly try launch_instance until it succeeds or the user Ctrl-C's.

    Shared by both shape flows in main.py (previously duplicated inline).
    """
    while True:
        interval = random.randint(
            max(interval_between_requests - 5, 1), interval_between_requests + 5
        )
        try:
            compute_client.launch_instance(instance_details)
            logger.info(success_message)
            telegram_notify(session, bot_api, chat_id, success_message)
            return
        except oci.exceptions.ServiceError as e:
            if e.status == 500:
                # Out of host capacity.
                message = f"❌ {e.message} Retry in {interval}s"
            elif e.status == 429:
                # TooManyRequests
                message = f"❌ {e.message} Retry in {interval}s"
            else:
                message = f"❌ {e} Retry in {interval}s"
                telegram_notify(session, bot_api, chat_id, message)
            logger.info(message)
            time.sleep(interval)
        except KeyboardInterrupt:
            session.close()
            sys.exit()
        except Exception as e:
            message = f"❌ {e} Retry in {interval}s"
            logger.info(message)
            telegram_notify(session, bot_api, chat_id, message)
            time.sleep(interval)

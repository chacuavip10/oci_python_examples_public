import oci
import logging
import os
import sys


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
        logging.critical(
            "❌ No available availability domain was found in your region")
        raise RuntimeError(
            "No available availability domain was found in your region")
    return list_availability_domains_response.data


def input_with_confirm_availability_domain(identity_client, compartment_id):

    list_of_availability_domain = get_availability_domain(
        identity_client=identity_client, compartment_id=compartment_id
    )
    # print(availability_domain)
    print("\nList of available domain in your region:")
    for index, domain_name in enumerate(list_of_availability_domain):
        print(f"\t[{index+1}]. {domain_name.name}")
    print()
    answer = None
    while True:
        print(
            'Go to https://cloud.oracle.com/compute/instances/create, choose "Always Free-eligible" Availability domain in the Placement tab and click Edit to view full name.'
        )
        print(
            '\n>>> Verify if "Always Free-eligible" Availability domain is listed above. If not, press [N].'
        )
        answer = input(">>> Confirm / Acknowledge [Y]es/[N]o: ")
        if answer in ("y", "Y"):
            break
        else:
            logging.error(
                'User not accept the confirmation or no available "Always Free-eligible" Availability domain. Script terminate automatically.'
            )
            sys.exit()

    domain_index = 1000
    while domain_index > len(list_of_availability_domain):
        answer = input(
            '\n>>> Choose the "Always Free-eligible" Availability domain [number index] in the list to continue. Press [s] to view the list again! '
        )

        if answer in ("s", "S"):
            print("List of available domain in your region:")
            for index, domain_name in enumerate(list_of_availability_domain):
                print(f"\t[{index+1}]. {domain_name.name}")
            print()
        else:
            try:
                domain_index = int(answer)
            except ValueError:
                print("❌ Must be a number")

    # Zero based index
    availability_domain = list_of_availability_domain[domain_index - 1]
    logging.info(
        f'👉 "Always Free-eligible" Availability Domain setting by user: {list_of_availability_domain[domain_index-1].name}'
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
    print("\nNote: At the time of 2022-03-30:")
    print(
        "\t- VM.Standard.A1.Flex is LIMITED_FREE, with total of 4 instances and 4 cpu - 24 GB Memory per account"
    )
    print(
        "\t- VM.Standard.E2.1.Micro is ALWAYS_FREE, with total of 2 instances per account"
    )
    print(
        "\t- Recheck at https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm to get last update"
    )
    print("\nList of free shape in your domain:")
    for index, shape in enumerate(free_shapes):
        print(f"\t[{index+1}]. {shape.shape}")
    print()
    shape_index = 1000
    while shape_index > len(free_shapes):
        answer = input(
            ">>> Choose the shape [number index] in the list to continue. Press [s] to view the list again! "
        )

        if answer in ("s", "S"):
            print("List of free shape in your domain:")
            for index, shape in enumerate(free_shapes):
                print(f"\t[{index+1}]. {shape.shape}")
            print()
        else:
            try:
                shape_index = int(answer)
            except ValueError:
                print("❌ Must be a number")

    # Zero based index
    shape_to_add = free_shapes[shape_index - 1]
    return shape_to_add


def input_with_config_image_to_add(compute_client, compartment_id, shape_to_add, os):
    all_images = get_image_for_shape(
        compute=compute_client,
        compartment_id=compartment_id,
        shape=shape_to_add,
        operating_system=os,
    )

    print("\nList of image compatible with your instance:")
    for index, image in enumerate(all_images):
        print(f"\t[{index+1}]. {image.display_name}")
    print()

    image_index = 1000
    while image_index > len(all_images):
        answer = input(
            ">>> Choose the image [number index] in the list to continue. Press [s] to view the list again! "
        )

        if answer in ("s", "S"):
            print("\nList of image compatible with your instance:")
            for index, image in enumerate(all_images):
                print(f"\t[{index+1}]. {image.display_name}")
            print()
        else:
            try:
                image_index = int(answer)
            except ValueError:
                print("❌ Must be a number")

    # Zero based index
    image_to_add = all_images[image_index - 1]
    return image_to_add


def list_all_instances(compute_client, config):
    results = compute_client.list_instances(
        compartment_id=config["tenancy"]).data

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
        logging.critical(
            "❌ No available network was found. Please create manually")
        raise RuntimeError(
            "No available network was found. Please create manually")

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
        logging.critical(
            "❌ No available subnet was found. Please create manually")
        raise RuntimeError(
            "No available subnet was found. Please create manually")

    return subnets


def get_boot_volume(storage_client, availability_domain, compartment_id) -> list:

    list_volumes_response = oci.pagination.list_call_get_all_results(
        storage_client.list_boot_volumes,
        availability_domain=availability_domain,
        compartment_id=compartment_id,
    )
    volumes = list_volumes_response.data
    # if len(volumes) == 0:
    #     raise RuntimeError('No available boot volume was found. Please create manually')

    return volumes


def get_block_volume(storage_client, compartment_id) -> list:

    list_volumes_response = oci.pagination.list_call_get_all_results(
        storage_client.list_volumes, compartment_id=compartment_id
    )
    volumes = list_volumes_response.data
    # if len(volumes) == 0:
    #     raise RuntimeError('No available boot volume was found. Please create manually')

    return volumes


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
    logging.info(
        "Check resources including the instance you try to create if any...")
    # Max 4 x VM.Standard.A1.Flex (4 ocpus/24GB), 2 x VM.Standard.E2.1.Micro
    free_exceed = False
    can_continue = True
    _a1_flex = _e2_1_micro = other_instances = 0
    _a1_flex_ocpus = _a1_flex_memory = 0
    instances_response = list_all_instances(
        compute_client=compute_client, config=config
    )

    if not instances_response:
        logging.info("✅ No compute instance (VM) found.")
    else:
        logging.info(f"{len(instances_response)} instances found!")
        logging.info(
            "⚠️  If instance in TERMINATING or TERMINATED state, script still count toward Free Tier resource. Please wait a day or two for OCI to clear."
        )
        for instance in instances_response:
            if instance.shape == "VM.Standard.E2.1.Micro":
                # and instance.lifecycle_state not in ("TERMINATING", "TERMINATED")
                _e2_1_micro += 1
                logging.info(
                    f"\t🖳 {instance.display_name: <20} | {instance.shape: <24} | {instance.lifecycle_state: <16} | 1 ocpu - 1GB RAM        |"
                )
            elif instance.shape == "VM.Standard.A1.Flex":
                # and instance.lifecycle_state not in ("TERMINATING", "TERMINATED")
                _a1_flex += 1
                _a1_flex_ocpus += float(instance.shape_config.ocpus)
                _a1_flex_memory += float(instance.shape_config.memory_in_gbs)
                logging.info(
                    f"\t🖳 {instance.display_name: <20} | {instance.shape: <24} | {instance.lifecycle_state: <16} | {instance.shape_config.ocpus} ocpus - {instance.shape_config.memory_in_gbs} GB RAM |"
                )
            else:
                other_instances += 1
                logging.info(
                    f"\t🖳 {instance.display_name: <20} | {instance.shape: <30} | {instance.lifecycle_state: <16} |"
                )

        if _a1_flex + future_to_add_number_of_a1_flex_instance > 4:
            free_exceed = True
            logging.warning(
                f"❌ VM.Standard.A1.Flex instances: Current {_a1_flex+future_to_add_number_of_a1_flex_instance} | Maximum: 4"
            )
        else:
            logging.info(
                f"✅ VM.Standard.A1.Flex instances: Current {_a1_flex+future_to_add_number_of_a1_flex_instance} | Maximum: 4"
            )

        if (
            _a1_flex_ocpus + future_to_add_a1_flex_ocpus > 4.0
            or _a1_flex_memory + future_to_add_a1_flex_memory > 24.0
        ):
            free_exceed = True
            logging.warning(
                f"❌ VM.Standard.A1.Flex resources: Current {_a1_flex_ocpus+future_to_add_a1_flex_ocpus} ocpus - {_a1_flex_memory+future_to_add_a1_flex_memory} GB Ram | Maximum: 4 ocpus - 24 GB Ram"
            )
        else:
            logging.info(
                f"✅ VM.Standard.A1.Flex resources: Current {_a1_flex_ocpus+future_to_add_a1_flex_ocpus} ocpus - {_a1_flex_memory+future_to_add_a1_flex_memory} GB Ram | Maximum: 4 ocpus - 24 GB Ram"
            )

        if _e2_1_micro + future_to_add_number_of_E2_1_Micro > 2:
            free_exceed = True
            logging.warning(
                f"❌ VM.Standard.E2.1.Micro instances: Current {_e2_1_micro+future_to_add_number_of_E2_1_Micro} | Maximum: 2"
            )
        else:
            logging.info(
                f"✅ VM.Standard.E2.1.Micro instances: Current {_e2_1_micro+future_to_add_number_of_E2_1_Micro} | Maximum: 2"
            )

        if other_instances > 0:
            free_exceed = True
            logging.warning(
                "❌ You have instance(s) shape not in Always Free-eligible program!"
            )

    # Checking VCN & Subnet
    try:
        vcns = get_vcn(network_client=network_client,
                       compartment_id=config["tenancy"])
        if len(vcns) > 2:
            free_exceed = True
            logging.warning(
                f"❌ Virtual Cloud Network: Current {len(vcns)} | Maximum: 2"
            )
        else:
            logging.info(
                f"✅ Virtual Cloud Network: Current {len(vcns)} | Maximum: 2")
            for vcn in vcns:
                logging.info(
                    f"\t☁️ VCN Name: {vcn.display_name} | IP Block: {vcn.cidr_block}"
                )
    except RuntimeError:
        can_continue = False
        logging.warning(
            "❌ No available Virtual Cloud Network was found. Please create manually"
        )

    try:
        subnets = get_subnet(
            network_client=network_client, compartment_id=config["tenancy"]
        )
        if len(subnets) > 0:
            logging.info(
                f"✅ At least 1 subnet found. Current {len(subnets)} | Maximum: N/A"
            )
            for subnet in subnets:
                logging.info(
                    f"\t🖧  Subnet Name: {subnet.display_name} | IP Block: {subnet.cidr_block}"
                )
    except RuntimeError:
        can_continue = False
        logging.warning(
            "❌ No available Virtual Cloud Network was found. Please create manually"
        )

    # Check storage
    print_storage = []
    boot_volumes_GBs_total = block_volumes_GBs_total = 0.0

    list_avai_domains = get_availability_domain(
        identity_client, compartment_id=config["tenancy"]
    )
    if list_avai_domains:
        boot_volume_response = []
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
        logging.warning(
            f"❌ Storage Size (Boot + Block Volumes): Current {boot_volumes_GBs_total + block_volumes_GBs_total} GBs | Maximum: 200 GBs"
        )
    else:
        logging.info(
            f"✅ Storage Size (Boot + Block Volumes): Current {boot_volumes_GBs_total + block_volumes_GBs_total} GBs | Maximum: 200 GBs"
        )
    for message in print_storage:
        logging.info(message)

    if free_exceed:
        logging.error("❌ Account exceed Free Tier resource limit!")
    elif not can_continue:
        logging.warning("Need manual step from user. Check log to proceed!")
    else:
        logging.info("✅ Account within Free Tier resource limit. Continue!")

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

    vm_shapes = list(
        filter(lambda shape: shape.shape.startswith("VM"), shapes))
    if len(vm_shapes) == 0:
        raise RuntimeError("No available VM shape was found.")

    return vm_shapes


def get_free_shape(compute_client, compartment_id, availability_domain) -> list:
    list_shapes_response = oci.pagination.list_call_get_all_results(
        compute_client.list_shapes,
        compartment_id,
        availability_domain=availability_domain.name,
    )

    shapes = list_shapes_response.data
    if len(shapes) == 0:
        raise RuntimeError("No available shape was found.")

    vm_shapes = list(
        filter(lambda shape: shape.shape.startswith("VM"), shapes))
    if len(vm_shapes) == 0:
        raise RuntimeError("No available VM shape was found.")

    free_shape = []
    for shape in vm_shapes:
        # print(shape)
        if (shape.billing_type in ["ALWAYS_FREE", "LIMITED_FREE"]) and (
            shape.shape in ["VM.Standard.E2.1.Micro"],
            ["VM.Standard.A1.Flex"],
        ):
            free_shape.append(shape)

    return free_shape


def choose_os():
    os = {
        1: "Oracle Linux Cloud Developer",
        2: "Oracle Linux",
        3: "Oracle Autonomous Linux",
        4: "CentOS",
        5: "Canonical Ubuntu",
    }
    print("\nChoosing os for instance!")
    print(f"[1]. {os[1]}")
    print(f"[2]. {os[2]}")
    print(f"[3]. {os[3]}")
    print(f"[4]. {os[4]}")
    print(f"[5]. {os[5]}")

    answer = 6
    while answer not in os.keys():
        try:
            answer = int(
                input(">>> Choose the os for instances [1 2 3 4 5]: "))
        except ValueError:
            print("❌ Must be a number")

    return os[answer]


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


# print(choose_os())
def telegram_setting(session):
    bot_api = None
    chat_id = None
    answer = input(
        "\n>>> Do you want to sent notification via Telegram? [Y]es/[N]o: ")

    if answer not in ("y", "Y"):
        return bot_api, chat_id
    else:
        telegram_answer = None

        while telegram_answer not in ("y", "Y"):
            bot_api = input(">>> Bot API key: ")
            chat_id = input(">>> chat_id: ")
            test_message = "[TEST] Hello from oci script!"
            session.get(
                f"https://api.telegram.org/bot{bot_api}/sendMessage?chat_id={chat_id}&text={test_message}"
            )

            telegram_answer = input(
                ">>> Did you get the test message? Press [y] if received or any key to reconfig the api key/chat id >>> "
            )

        logging.info(f"👉 Telegram notification is enabled")
    return bot_api, chat_id


def telegram_notify(session, bot_api, chat_id, message):
    """Notify via telegram"""
    try:
        session.get(
            f"https://api.telegram.org/bot{bot_api}/sendMessage?chat_id={chat_id}&text={message}"
        )
    except:
        logging.info("Message fail to sent via telegram")


def gen_random_instance_name():
    import random

    instance_name = "instance-" + "".join(
        random.SystemRandom().choice(
            ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
        )
        for _ in range(10)
    )
    # print(instance_name)
    return instance_name


def gen_ssh_keygen():
    ssh_key = ""
    from pathlib import Path
    import subprocess

    ssh_pub_key = Path(".") / "script_ssh_key_autogen.pub"
    ssh_priv_key = Path(".") / "script_ssh_key_autogen"

    if ssh_pub_key.exists() and ssh_priv_key.exists():
        logging.info(f"SSH key found. {str(ssh_priv_key)}")
    else:
        logging.info(
            f"Create new ssh key pair, you can use this to login to your newly created instance."
        )
        logging.info(
            f"Feature are still in testing. Please also provide your ssh-key."
        )
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
            ]
        )
    except:
        logging.warning("❌ Fail to create ssh-key-pair using ssh-keygen")
    try:
        with open(ssh_pub_key, "r") as f:
            ssh_key = f.read().strip()
        logging.info(f"Script generated ssh-key: {ssh_key}")
        logging.info(
            f"📌 Login usage: ssh -i script_ssh_key_autogen user@ip. Passphrase will be <empty passphrase>")
    except:
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
            logging.debug(f"👉 User input custom ssh-key: {user_ssh_key}")
        else:
            logging.info("User not input ssh-key. Only using default key.")
            break
    return user_ssh_key


def input_interval_between_request():
    logging.warning(
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

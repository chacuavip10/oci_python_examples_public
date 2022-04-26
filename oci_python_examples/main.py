from helper_func import *
import sys
from pathlib import Path

clear_scr()

print("\n⚠️ ⚠️ ⚠️  Make sure your OCI account is in Free Tier only before proceed!")
print(
    'Go to https://cloud.oracle.com to verify! You should see a banner with "your account will be limited to Always Free resources. Upgrade at any time."'
)
answer = input(">>> Confirm / Acknowledge [Y]es/[N]o: ")
if answer not in ("y", "Y"):
    sys.exit()

LOG_FORMAT = "[%(levelname)s] %(asctime)s - %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("oci.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

BASE_DIR = Path(__file__).resolve().parent.parent
config_path = BASE_DIR / 'env/config'

logging.debug("Loading config file...")
try:
    config = oci.config.from_file(
        file_location=str(config_path)
    )
except oci.exceptions.ConfigFileNotFound:
    logging.error(
        "Config file not found. Please put the config and oci_private_key.pem file in the evn folder!")
    sys.exit()
except oci.exceptions.InvalidKeyFilePath:
    logging.error(
        "Private key file not found. Please put the config and oci_private_key.pem file in the evn folder!")
    sys.exit()

logging.debug("Initialize oci client!")
identity_client = oci.identity.IdentityClient(config)
compute_client = oci.core.ComputeClient(config=config)
network_client = oci.core.VirtualNetworkClient(config=config)
storage_client = oci.core.BlockstorageClient(config=config)
# Demo only
list_of_availability_domain = get_availability_domain(
    identity_client=identity_client, compartment_id=config["tenancy"]
)[0]


if __name__ == "__main__":
    # Root compartment
    compartment_id = config["tenancy"]
    logging.info(
        f"Setting root compartment: {compartment_id[:40] + '**********'}")

    message = """
#################################################################
# 1. Check current resource in account                          #
# 2. Create new Free VM                                         #
#################################################################"""
    print(message)

    choice = None
    while choice not in (1, 2):
        try:
            choice = int(input(">>> Enter your choice: [1 2]: "))
        except ValueError:
            print("❌ Must be a number")

    if choice == 1:
        logging.info("[Check current resource in account]")
        free_tier_check(
            identity_client=identity_client,
            compute_client=compute_client,
            network_client=network_client,
            storage_client=storage_client,
            config=config,
        )
        logging.warning(
            "[Check current resource in account] Done. Script terminate automatically")
        sys.exit()

    # Get availability_domain to create instances
    availability_domain = input_with_confirm_availability_domain(
        identity_client=identity_client, compartment_id=compartment_id
    )

    if choice == 2:
        (
            future_to_add_a1_flex_ocpus,
            future_to_add_a1_flex_memory,
            future_to_add_number_of_E2_1_Micro,
        ) = (None, None, 1)
        import requests

        session = requests.Session()

        logging.info(
            "[Create new Free VM] Note: Script will assign random name for your instance, you can change it later in the Web Console."
        )
        # loggin
        bot_api, chat_id = telegram_setting(session=session)

        shape_to_add = input_with_confirm_free_shape_to_add(
            compute_client=compute_client,
            compartment_id=compartment_id,
            availability_domain=availability_domain,
        )
        logging.info(
            f"👉 User choose to create instance of '{shape_to_add.shape}'")

        if shape_to_add.shape == "VM.Standard.E2.1.Micro":
            logging.warning(
                "⚠️  Oracle policy: Instances using the VM.Standard.E2.1.Micro shape can only be created in one availability domain")
            try:
                future_to_add_number_of_E2_1_Micro = int(
                    input(
                        f"\n>>> Number of {shape_to_add.shape} instances to create: ")
                )
                if future_to_add_number_of_E2_1_Micro == 0:
                    logging.info("User choose 0. Exiting!")
                    logging.warning("Script terminate automatically")
                    sys.exit()
            except ValueError:
                print("❌ Must be a number")

            logging.info(
                f"User creating {future_to_add_number_of_E2_1_Micro} instance of {shape_to_add.shape}."
            )
            logging.info("[Create new Free VM] Initiate precheck")
            # Recheck
            if future_to_add_number_of_E2_1_Micro:
                _continue = free_tier_check(
                    identity_client=identity_client,
                    compute_client=compute_client,
                    network_client=network_client,
                    storage_client=storage_client,
                    config=config,
                    future_to_add_number_of_E2_1_Micro=future_to_add_number_of_E2_1_Micro,
                )

                # TODO Bypass precheck E1
                if not _continue:
                    logging.error(
                        "[Create new Free VM] Precheck fail. Script terminate automatically")
                    sys.exit()

        if shape_to_add.shape == "VM.Standard.A1.Flex":
            logging.info(
                f"Script only support create 1 instance of {shape_to_add.shape} per run!"
            )
            print(
                "\nInput shape config (cpu/ram). Rerun script if necessary to check free resource!"
            )
            future_to_add_a1_flex_ocpus = future_to_add_a1_flex_memory = 1000
            while future_to_add_a1_flex_ocpus > 4 or future_to_add_a1_flex_ocpus <= 0:
                try:
                    future_to_add_a1_flex_ocpus = int(
                        input(
                            ">>> Choose the cpu core count (0 < n <= 4). Memory will be cpu * 6: "
                        )
                    )
                except ValueError:
                    print("❌ Must be a number")

            future_to_add_a1_flex_memory = future_to_add_a1_flex_ocpus * 6
            logging.info(
                f"👉 User choose to create 1 instance of {shape_to_add.shape} with {future_to_add_a1_flex_ocpus} ocpus / {future_to_add_a1_flex_memory} GB"
            )

            # Precheck
            _continue = free_tier_check(
                identity_client=identity_client,
                compute_client=compute_client,
                network_client=network_client,
                storage_client=storage_client,
                config=config,
                future_to_add_number_of_a1_flex_instance=1,
                future_to_add_a1_flex_ocpus=future_to_add_a1_flex_ocpus,
                future_to_add_a1_flex_memory=future_to_add_a1_flex_memory,
            )
            # TODO Bypass precheck A1
            if not _continue:
                logging.error(
                    "[Create new Free VM] Precheck fail. Script terminate automatically")
                sys.exit()

        # Choosing os to search for image
        os = choose_os()
        logging.info(f"👉 User choose OS: {os}")

        # Get image
        image_to_add = input_with_config_image_to_add(
            compute_client=compute_client,
            compartment_id=compartment_id,
            shape_to_add=shape_to_add,
            os=os,
        )
        logging.info(
            f"👉 Instance setting updated | image: {image_to_add.display_name} | image_id: {image_to_add.id}"
        )
        # Subnet config
        subnet_id = None

        subnet_response = get_subnet(
            network_client=network_client, compartment_id=compartment_id
        )

        if len(subnet_response) == 1:
            print("\nList of subnet in your account:")
            for index, subnet in enumerate(subnet_response):
                print(f"\t[{index+1}]. {subnet.display_name}")
            print()
            subnet_id = subnet_response[0].id
            logging.info(
                f"Only 1 subnet found. Choosing subnet {subnet_response[0].id} as instance subnet"
            )
        elif len(subnet_response) > 1:
            print("\nList of subnet in your account:")
            for index, subnet in enumerate(subnet_response):
                print(f"\t[{index+1}]. {subnet.display_name}")
            print()
            answer = None

            subnet_index = 1000
            while subnet_index > len(subnet_response):
                answer = input(
                    ">>> Choose the subnet [number index] in the list to continue. Press [s] to view the list again! "
                )

                if answer in ("s", "S"):
                    print("List of subnet in your account:")
                    for index, subnet in enumerate(subnet_response):
                        print(f"\t[{index+1}]. {subnet.display_name}")
                    print()
                else:
                    try:
                        subnet_index = int(answer)
                    except ValueError:
                        print("❌ Must be a number")
                subnet_id = subnet_response[subnet_index - 1].id
        else:
            logging.error(
                "Can't not get the subnet from account. Script terminate automatically")
            sys.exit()

        # SSH-KEY Config
        script_ssh_key = gen_ssh_keygen()
        user_ssh_key = input_user_ssh_key()
        final_ssh_key = "\n".join([script_ssh_key, user_ssh_key])
        logging.info(f"👉 Instance setting updated | {final_ssh_key=}")

        # Request interval config (random +-5 s)
        interval_between_requests = input_interval_between_request()
        logging.info(
            f"👉 Request setting updated | {interval_between_requests=}")

        # Show user all info about instance about to create
        instance_message = None
        if shape_to_add.shape == "VM.Standard.E2.1.Micro":
            instance_message = f"👉 User choose to create | {future_to_add_number_of_E2_1_Micro}x {shape_to_add.shape} with {image_to_add.display_name} | image_id: {image_to_add.id} | Availability domain: {availability_domain.name}"
            logging.info(instance_message)
            print()
            print(
                "##############################    Instance info    ##############################"
            )
            print(
                f">> {future_to_add_number_of_E2_1_Micro}x {shape_to_add.shape}")
            print(f">> Subnet {subnet_id}")
            print(f">> os: {os} | image: {image_to_add.display_name}")
            print(f">> Availability domain: {availability_domain.name}")
            print(
                "############################## End of instance info ##############################"
            )
            print()

        if shape_to_add.shape == "VM.Standard.A1.Flex":
            instance_message = f"👉 User choose to create | 1x {shape_to_add.shape} with {image_to_add.display_name} | image_id: {image_to_add.id} | Availability domain: {availability_domain.name}"
            logging.info(instance_message)
            print()
            print(
                "##############################    Instance info    ##############################"
            )
            print(f">> 1x {shape_to_add.shape}")
            print(
                f">> Shape config: {future_to_add_a1_flex_ocpus} ocpus - {future_to_add_a1_flex_memory} GB"
            )
            print(f">> Subnet {subnet_id}")
            print(f">> os: {os} | image {image_to_add.display_name}")
            print(f">> Availability domain: {availability_domain.name}")
            print(
                "############################## End of instance info ##############################"
            )
            print()

        # Ask for confirmation before create instance
        print(
            'Go to https://cloud.oracle.com/compute/instances/create, check if availability domain, shape, image/os has "Always Free-eligible" tag.'
        )
        answer = input(
            ">>> Confirm / Acknowledge [Y]es/[N]o: ")
        if answer not in ("y", "Y"):
            logging.error(
                "User not accept the confirmation or no available \"Always Free-eligible\". Script terminate automatically.")
            sys.exit()

        telegram_notify(
            session=session, bot_api=bot_api, chat_id=chat_id, message=instance_message
        )

        # LAUNCH INSTANCE
        print(
            "Now the script will try to create instance with above setting...")
        logging.info(
            "Compute Instance Monitoring is disabled by script to limit logging storage exceed for your free tier, you can enable it in instance setting"
        )

        import random
        import time

        instance_detail = None

        if shape_to_add.shape == "VM.Standard.A1.Flex":
            instance_display_name = gen_random_instance_name()
            logging.info(f"Instance display name set: {instance_display_name}")
            instance_detail = oci.core.models.LaunchInstanceDetails(
                metadata={"ssh_authorized_keys": final_ssh_key},
                availability_domain=availability_domain.name,
                shape=shape_to_add.shape,
                compartment_id=compartment_id,
                display_name=instance_display_name,
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    source_type="image", image_id=image_to_add.id
                ),
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    assign_public_ip=False,
                    subnet_id=subnet_id,
                    assign_private_dns_record=True,
                ),
                agent_config=oci.core.models.LaunchInstanceAgentConfigDetails(
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
                defined_tags={},
                freeform_tags={},
                instance_options=oci.core.models.InstanceOptions(
                    are_legacy_imds_endpoints_disabled=False
                ),
                availability_config=oci.core.models.LaunchInstanceAvailabilityConfigDetails(
                    recovery_action="RESTORE_INSTANCE"
                ),
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    ocpus=future_to_add_a1_flex_ocpus,
                    memory_in_gbs=future_to_add_a1_flex_memory,
                ),
            )

            # Launch A1 Flex
            to_try = True
            while to_try:
                interval = random.randint(
                    interval_between_requests - 5, interval_between_requests + 5
                )
                try:
                    compute_client.launch_instance(instance_detail)
                    to_try = False
                    message = "✅ Success! Edit vnic to get public ip address"
                    logging.info(message)
                    telegram_notify(session, bot_api, chat_id, message)
                except oci.exceptions.ServiceError as e:
                    if e.status == 500:
                        # Out of host capacity.
                        message = f"❌ {e.message} Retry in {interval}s"
                        # telegram_notify(session, bot_api, chat_id, message)
                    else:
                        message = f"❌ {e} Retry in {interval}s"
                        telegram_notify(session, bot_api, chat_id, message)
                    logging.info(message)
                    time.sleep(interval)
                except KeyboardInterrupt:
                    session.close()
                    sys.exit()
                except Exception as e:
                    message = f"❌ {e} Retry in {interval}s"
                    logging.info(message)
                    telegram_notify(session, bot_api, chat_id, message)
                    time.sleep(interval)

        if shape_to_add.shape == "VM.Standard.E2.1.Micro":
            current_instance_to_create = 0
            while current_instance_to_create < future_to_add_number_of_E2_1_Micro:
                instance_display_name = gen_random_instance_name()
                message = f"Create instance {current_instance_to_create+1}/{future_to_add_number_of_E2_1_Micro}. Display name set: {instance_display_name}"
                logging.info(message)
                telegram_notify(session, bot_api, chat_id, message)

                instance_detail = oci.core.models.LaunchInstanceDetails(
                    metadata={"ssh_authorized_keys": final_ssh_key},
                    availability_domain=availability_domain.name,
                    shape=shape_to_add.shape,
                    compartment_id=compartment_id,
                    display_name=instance_display_name,
                    source_details=oci.core.models.InstanceSourceViaImageDetails(
                        source_type="image", image_id=image_to_add.id
                    ),
                    create_vnic_details=oci.core.models.CreateVnicDetails(
                        assign_public_ip=True,
                        subnet_id=subnet_id,
                        assign_private_dns_record=True,
                    ),
                    agent_config=oci.core.models.LaunchInstanceAgentConfigDetails(
                        is_monitoring_disabled=False,
                        is_management_disabled=False,
                        plugins_config=[
                            oci.core.models.InstanceAgentPluginConfigDetails(
                                name="Vulnerability Scanning", desired_state="DISABLED"
                            ),
                            oci.core.models.InstanceAgentPluginConfigDetails(
                                name="Compute Instance Monitoring",
                                desired_state="DISABLED",
                            ),
                            oci.core.models.InstanceAgentPluginConfigDetails(
                                name="Bastion", desired_state="DISABLED"
                            ),
                        ],
                    ),
                    defined_tags={},
                    freeform_tags={},
                    instance_options=oci.core.models.InstanceOptions(
                        are_legacy_imds_endpoints_disabled=False
                    ),
                    availability_config=oci.core.models.LaunchInstanceAvailabilityConfigDetails(
                        recovery_action="RESTORE_INSTANCE"
                    ),
                )

                to_try = True
                while to_try:
                    interval = random.randint(
                        interval_between_requests - 5, interval_between_requests + 5
                    )
                    try:
                        compute_client.launch_instance(instance_detail)
                        to_try = False
                        message = "✅ Success! Go to web console to get the public ip address of instance."
                        logging.info(message)
                        telegram_notify(session, bot_api, chat_id, message)
                        # print(to_launch_instance.data)
                    except oci.exceptions.ServiceError as e:
                        if e.status == 500:
                            # Out of host capacity.
                            message = f"❌ {e.message} Retry in {interval}s"
                            # telegram_notify(session, bot_api, chat_id, message)
                        else:
                            message = f"❌ {e} Retry in {interval}s"
                            telegram_notify(session, bot_api, chat_id, message)
                        logging.info(message)
                        time.sleep(interval)
                    except KeyboardInterrupt:
                        session.close()
                        sys.exit()
                    except Exception as e:
                        message = f"❌ {e} Retry in {interval}s"
                        logging.info(message)
                        telegram_notify(session, bot_api, chat_id, message)
                        time.sleep(interval)

                current_instance_to_create += 1

        # Close session
        session.close()
        logging.info(
            "[Create new Free VM] Create instance successfully. Script terminate automatically.")

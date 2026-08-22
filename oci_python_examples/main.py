import logging
import sys
from pathlib import Path

import oci
from helper_func import *

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

logger = logging.getLogger()

BASE_DIR = Path(__file__).resolve().parent.parent
config_path = BASE_DIR / "env/config"

logger.debug("Loading config file...")
try:
    config = oci.config.from_file(file_location=str(config_path))
except oci.exceptions.ConfigFileNotFound:
    logger.error(
        "Config file not found. Please put the config and oci_private_key.pem file in the evn folder!"
    )
    sys.exit()
except oci.exceptions.InvalidKeyFilePath:
    logger.error(
        "Private key file not found. Please put the config and oci_private_key.pem file in the evn folder!"
    )
    sys.exit()

logger.debug("Initialize oci client!")
identity_client = oci.identity.IdentityClient(config)
compute_client = oci.core.ComputeClient(config=config)
network_client = oci.core.VirtualNetworkClient(config=config)
storage_client = oci.core.BlockstorageClient(config=config)
# NOTE: removed a stray call here that fetched availability domains just to
# discard the result — input_with_confirm_availability_domain() below fetches
# them again when actually needed, so the extra API call was pure overhead.


if __name__ == "__main__":
    # Root compartment
    compartment_id = config["tenancy"]
    logger.info(f"Setting root compartment: {compartment_id[:40] + '**********'}")

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
        logger.info("[Check current resource in account]")
        free_tier_check(
            identity_client=identity_client,
            compute_client=compute_client,
            network_client=network_client,
            storage_client=storage_client,
            config=config,
        )
        logger.warning(
            "[Check current resource in account] Done. Script terminate automatically"
        )
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

        logger.info(
            "[Create new Free VM] Note: Script will assign random name for your instance, you can change it later in the Web Console."
        )
        bot_api, chat_id = telegram_setting(session=session)

        shape_to_add = input_with_confirm_free_shape_to_add(
            compute_client=compute_client,
            compartment_id=compartment_id,
            availability_domain=availability_domain,
        )
        logger.info(f"👉 User choose to create instance of '{shape_to_add.shape}'")

        if shape_to_add.shape == "VM.Standard.E2.1.Micro":
            logger.warning(
                "⚠️  Oracle policy: Instances using the VM.Standard.E2.1.Micro shape can only be created in one availability domain"
            )
            future_to_add_number_of_E2_1_Micro = None
            while future_to_add_number_of_E2_1_Micro is None:
                try:
                    future_to_add_number_of_E2_1_Micro = int(
                        input(
                            f"\n>>> Number of {shape_to_add.shape} instances to create: "
                        )
                    )
                except ValueError:
                    print("❌ Must be a number")

            if future_to_add_number_of_E2_1_Micro == 0:
                logger.info("User choose 0. Exiting!")
                logger.warning("Script terminate automatically")
                sys.exit()

            logger.info(
                f"User creating {future_to_add_number_of_E2_1_Micro} instance of {shape_to_add.shape}."
            )
            logger.info("[Create new Free VM] Initiate precheck")
            _continue = free_tier_check(
                identity_client=identity_client,
                compute_client=compute_client,
                network_client=network_client,
                storage_client=storage_client,
                config=config,
                future_to_add_number_of_E2_1_Micro=future_to_add_number_of_E2_1_Micro,
            )

            if not _continue:
                logger.error(
                    "[Create new Free VM] Precheck fail. Script terminate automatically"
                )
                sys.exit()

        if shape_to_add.shape == "VM.Standard.A1.Flex":
            logger.info(
                f"Script only support create 1 instance of {shape_to_add.shape} per run!"
            )
            print(
                "\nInput shape config (cpu/ram). Rerun script if necessary to check free resource!"
            )
            future_to_add_a1_flex_ocpus = 1000
            while future_to_add_a1_flex_ocpus > 2 or future_to_add_a1_flex_ocpus <= 0:
                try:
                    future_to_add_a1_flex_ocpus = int(
                        input(
                            ">>> Choose the cpu core count (0 < n <= 2). Memory will be cpu * 6: "
                        )
                    )
                except ValueError:
                    print("❌ Must be a number")

            future_to_add_a1_flex_memory = future_to_add_a1_flex_ocpus * 6
            logger.info(
                f"👉 User choose to create 1 instance of {shape_to_add.shape} with {future_to_add_a1_flex_ocpus} ocpus / {future_to_add_a1_flex_memory} GB"
            )

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
            if not _continue:
                logger.error(
                    "[Create new Free VM] Precheck fail. Script terminate automatically"
                )
                sys.exit()

        # Choosing os to search for image
        os = choose_os()
        logger.info(f"👉 User choose OS: {os}")

        # Get image
        image_to_add = input_with_config_image_to_add(
            compute_client=compute_client,
            compartment_id=compartment_id,
            shape_to_add=shape_to_add,
            os=os,
        )
        logger.info(
            f"👉 Instance setting updated | image: {image_to_add.display_name} | image_id: {image_to_add.id}"
        )

        # Subnet config
        subnet_response = get_subnet(
            network_client=network_client, compartment_id=compartment_id
        )

        if len(subnet_response) == 1:
            subnet_id = subnet_response[0].id
            logger.info(
                f"Only 1 subnet found. Choosing subnet {subnet_id} as instance subnet"
            )
        elif len(subnet_response) > 1:
            subnet = select_from_list(
                [s.display_name for s in subnet_response],
                "List of subnet in your account:",
                "subnet",
            )
            subnet_id = next(s.id for s in subnet_response if s.display_name == subnet)
        else:
            logger.error(
                "Can't not get the subnet from account. Script terminate automatically"
            )
            sys.exit()

        # SSH-KEY Config
        script_ssh_key = gen_ssh_keygen()
        user_ssh_key = input_user_ssh_key()
        final_ssh_key = f"{script_ssh_key}\n{user_ssh_key}"
        logger.info("👉 Instance setting updated | ssh key(s) configured (not logged)")

        # Request interval config (random +-5 s)
        interval_between_requests = input_interval_between_request()
        logger.info(f"👉 Request setting updated | {interval_between_requests=}")

        # Show user all info about instance about to create
        instance_message = None
        if shape_to_add.shape == "VM.Standard.E2.1.Micro":
            instance_message = f"👉 User choose to create | {future_to_add_number_of_E2_1_Micro}x {shape_to_add.shape} with {image_to_add.display_name} | image_id: {image_to_add.id} | Availability domain: {availability_domain.name}"
            logger.info(instance_message)
            print()
            print(
                "##############################    Instance info    ##############################"
            )
            print(f">> {future_to_add_number_of_E2_1_Micro}x {shape_to_add.shape}")
            print(f">> Subnet {subnet_id}")
            print(f">> os: {os} | image: {image_to_add.display_name}")
            print(f">> Availability domain: {availability_domain.name}")
            print(
                "############################## End of instance info ##############################"
            )
            print()

        if shape_to_add.shape == "VM.Standard.A1.Flex":
            instance_message = f"👉 User choose to create | 1x {shape_to_add.shape} with {image_to_add.display_name} | image_id: {image_to_add.id} | Availability domain: {availability_domain.name}"
            logger.info(instance_message)
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
        answer = input(">>> Confirm / Acknowledge [Y]es/[N]o: ")
        if answer not in ("y", "Y"):
            logger.error(
                'User not accept the confirmation or no available "Always Free-eligible". Script terminate automatically.'
            )
            sys.exit()

        telegram_notify(
            session=session, bot_api=bot_api, chat_id=chat_id, message=instance_message
        )

        # LAUNCH INSTANCE
        print("Now the script will try to create instance with above setting...")
        logger.info(
            "Compute Instance Monitoring is disabled by script to limit logging storage exceed for your free tier, you can enable it in instance setting"
        )

        if shape_to_add.shape == "VM.Standard.A1.Flex":
            instance_display_name = gen_random_instance_name()
            logger.info(f"Instance display name set: {instance_display_name}")

            instance_detail = build_launch_instance_details(
                availability_domain=availability_domain.name,
                compartment_id=compartment_id,
                shape=shape_to_add.shape,
                display_name=instance_display_name,
                image_id=image_to_add.id,
                subnet_id=subnet_id,
                ssh_authorized_keys=final_ssh_key,
                assign_public_ip=False,
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    ocpus=future_to_add_a1_flex_ocpus,
                    memory_in_gbs=future_to_add_a1_flex_memory,
                ),
            )
            launch_instance_with_retry(
                compute_client=compute_client,
                instance_details=instance_detail,
                interval_between_requests=interval_between_requests,
                session=session,
                bot_api=bot_api,
                chat_id=chat_id,
                success_message="✅ Success! Edit vnic to get public ip address",
            )

        if shape_to_add.shape == "VM.Standard.E2.1.Micro":
            for i in range(future_to_add_number_of_E2_1_Micro):
                instance_display_name = gen_random_instance_name()
                message = (
                    f"Create instance {i + 1}/{future_to_add_number_of_E2_1_Micro}. "
                    f"Display name set: {instance_display_name}"
                )
                logger.info(message)
                telegram_notify(session, bot_api, chat_id, message)

                instance_detail = build_launch_instance_details(
                    availability_domain=availability_domain.name,
                    compartment_id=compartment_id,
                    shape=shape_to_add.shape,
                    display_name=instance_display_name,
                    image_id=image_to_add.id,
                    subnet_id=subnet_id,
                    ssh_authorized_keys=final_ssh_key,
                    assign_public_ip=True,
                )
                launch_instance_with_retry(
                    compute_client=compute_client,
                    instance_details=instance_detail,
                    interval_between_requests=interval_between_requests,
                    session=session,
                    bot_api=bot_api,
                    chat_id=chat_id,
                    success_message="✅ Success! Go to web console to get the public ip address of instance.",
                )

        # Close session
        session.close()
        logger.info(
            "[Create new Free VM] Create instance successfully. Script terminate automatically."
        )

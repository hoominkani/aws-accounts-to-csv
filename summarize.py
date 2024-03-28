import logging
from datetime import datetime
from itertools import product
from operator import itemgetter
from typing import Dict, List, Tuple

import boto3
from tabulate import tabulate

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
TEMPLATE = """# AWS IAM Identity Center Inventory

- Retrieved at: {datetime}
- Executed Account: {account_name} ({account_id})

## IAM Identity Center Information

- Instance ARN: {instance_arn}
- Identity Store ID: {identity_store_id}

## AWS Accounts

{accounts}

## Users

{users}

## Groups

{groups}

## Group Memberships

{group_memberships}

## Permission Sets

{permission_sets}

## Assignments

{assignments}
"""


class IdentityCenterInventory:
    """
    Class to generate an inventory report for AWS IAM Identity Center.
    """

    def __init__(self):
        self.org_client = boto3.client('organizations')
        self.idstore_client = boto3.client('identitystore')
        self.ssoadmin_client = boto3.client('sso-admin')
        self.sts_client = boto3.client('sts')

        self.accounts = []
        self.account_id_to_name = {}
        self.users = []
        self.user_id_to_name = {}
        self.groups = []
        self.group_id_to_name = {}
        self.permission_sets = []
        self.permission_set_arn_to_name = {}

    def fetch_accounts(self) -> None:
        """
        Fetches AWS accounts from AWS Organizations.
        """
        logging.info('Fetching AWS accounts...')
        paginator = self.org_client.get_paginator('list_accounts')
        for page in paginator.paginate():
            self.accounts.extend(page['Accounts'])
        self.account_id_to_name = {account['Id']: account['Name'] for account in self.accounts}
        logging.info(f'Number of accounts: {len(self.account_id_to_name)}')

    def fetch_users(self, identity_store_id: str) -> None:
        """
        Fetches users from the specified Identity Store.

        Args:
            identity_store_id (str): The ID of the Identity Store.
        """
        logging.info('Fetching users...')
        paginator = self.idstore_client.get_paginator('list_users')
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            self.users.extend(page['Users'])
        self.user_id_to_name = {user['UserId']: user['DisplayName'] for user in self.users}
        logging.info(f'Number of users: {len(self.user_id_to_name)}')

    def fetch_groups(self, identity_store_id: str) -> None:
        """
        Fetches groups from the specified Identity Store.

        Args:
            identity_store_id (str): The ID of the Identity Store.
        """
        logging.info('Fetching groups...')
        paginator = self.idstore_client.get_paginator('list_groups')
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            self.groups.extend(page['Groups'])
        self.group_id_to_name = {group['GroupId']: group['DisplayName'] for group in self.groups}
        logging.info(f'Number of groups: {len(self.group_id_to_name)}')

    def fetch_permission_sets(self, instance_arn: str) -> None:
        """
        Fetches permission sets from the specified IAM Identity Center instance.

        Args:
            instance_arn (str): The ARN of the IAM Identity Center instance.
        """
        logging.info('Fetching permission sets...')
        paginator = self.ssoadmin_client.get_paginator('list_permission_sets')
        permission_set_arns = []
        for page in paginator.paginate(InstanceArn=instance_arn):
            permission_set_arns.extend(page['PermissionSets'])

        for arn in permission_set_arns:
            permission_set = self.ssoadmin_client.describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=arn
            )['PermissionSet']
            self.permission_sets.append(permission_set)
            self.permission_set_arn_to_name[arn] = permission_set['Name']

        logging.info(f'Number of permission sets: {len(self.permission_set_arn_to_name)}')

    def fetch_group_memberships(self, identity_store_id: str) -> List[Tuple[str, str]]:
        """
        Fetches group memberships from the specified Identity Store.

        Args:
            identity_store_id (str): The ID of the Identity Store.

        Returns:
            List[Tuple[str, str]]: A list of tuples (group_name, user_name) representing group memberships.
        """
        logging.info('Fetching group memberships...')
        memberships = []
        for group_id, group_name in self.group_id_to_name.items():
            paginator = self.idstore_client.get_paginator('list_group_memberships')
            for page in paginator.paginate(IdentityStoreId=identity_store_id, GroupId=group_id):
                for membership in page['GroupMemberships']:
                    user_id = membership['MemberId']['UserId']
                    user_name = self.user_id_to_name.get(user_id, f'#DELETED({user_id})')
                    memberships.append((group_name, user_name))
        logging.info(f'Number of group memberships: {len(memberships)}')
        return memberships

    def fetch_assignments(self, instance_arn: str) -> List[Tuple[str, str, str, str]]:
        """
        Fetches account assignments for the specified IAM Identity Center instance.

        Args:
            instance_arn (str): The ARN of the IAM Identity Center instance.

        Returns:
            List[Tuple[str, str, str, str]]: A list of tuples (account_name, principal_type, principal_name, permission_set_name) representing assignments.
        """
        logging.info('Fetching account assignments...')
        assignments = []
        for account_id, permission_set_arn in product(self.account_id_to_name.keys(), self.permission_set_arn_to_name.keys()):
            account_name = self.account_id_to_name[account_id]
            permission_set_name = self.permission_set_arn_to_name[permission_set_arn]
            logging.info(f'Fetching assignments for {account_name}, {permission_set_name}...')
            paginator = self.ssoadmin_client.get_paginator('list_account_assignments')
            for page in paginator.paginate(InstanceArn=instance_arn, AccountId=account_id, PermissionSetArn=permission_set_arn):
                for assignment in page['AccountAssignments']:
                    principal_type = assignment['PrincipalType']
                    principal_id = assignment['PrincipalId']
                    if principal_type == 'USER':
                        principal_name = self.user_id_to_name.get(principal_id, f'#DELETED({principal_id})')
                    elif principal_type == 'GROUP':
                        principal_name = self.group_id_to_name.get(principal_id, f'#DELETED({principal_id})')
                    else:
                        principal_name = f'#UNKNOWN({principal_id})'
                    assignments.append((account_name, principal_type, principal_name, permission_set_name))
        logging.info(f'Number of assignments: {len(assignments)}')
        return assignments

    def generate_report(self) -> None:
        """
        Generates the inventory report and saves it to a file.
        """
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        logging.info('Generating inventory report...')

        # Fetch account information
        self.fetch_accounts()
        exec_account_id = self.sts_client.get_caller_identity()['Account']
        exec_account_name = self.account_id_to_name.get(exec_account_id, 'Unknown')

        # Fetch IAM Identity Center instance information
        instances = self.ssoadmin_client.list_instances()['Instances']
        if not instances:
            logging.error('No IAM Identity Center instance found.')
            return
        instance_arn = instances[0]['InstanceArn']
        identity_store_id = instances[0]['IdentityStoreId']

        # Fetch users and groups
        self.fetch_users(identity_store_id)
        self.fetch_groups(identity_store_id)

        # Fetch permission sets
        self.fetch_permission_sets(instance_arn)

        # Fetch group memberships and assignments
        group_memberships = self.fetch_group_memberships(identity_store_id)
        assignments = self.fetch_assignments(instance_arn)

        # Generate tabulated data
        accounts_table = tabulate(
            sorted([(name, account_id) for account_id, name in self.account_id_to_name.items()], key=itemgetter(0)),
            headers=['Account Name', 'Account ID'],
            tablefmt='github'
        )
        users_table = tabulate(
            sorted([(display_name, user_name, user_id) for user_id, display_name in self.user_id_to_name.items() for user_name, user_id in [(None, user_id)]], key=itemgetter(0, 1)),
            headers=['Display Name', 'User Name', 'User ID'],
            tablefmt='github'
        )
        groups_table = tabulate(
            sorted([(display_name, description, group_id) for group_id, display_name in self.group_id_to_name.items() for description, group_id in [(None, group_id)]], key=itemgetter(0)),
            headers=['Display Name', 'Description', 'Group ID'],
            tablefmt='github'
        )
        group_memberships_table = tabulate(
            sorted(group_memberships, key=itemgetter(0, 1)),
            headers=['Group Name', 'User Name'],
            tablefmt='github'
        )
        permission_sets_table = tabulate(
            sorted([(name, description, arn) for arn, name in self.permission_set_arn_to_name.items() for description, arn in [(None, arn)]], key=itemgetter(0)),
            headers=['Permission Set Name', 'Description', 'Permission Set ARN'],
            tablefmt='github'
        )
        assignments_table = tabulate(
            sorted(assignments, key=itemgetter(0, 1, 2)),
            headers=['Account Name', 'Principal Type', 'Principal Name', 'Permission Set Name'],
            tablefmt='github'
        )

        # Generate report
        report = TEMPLATE.format(
            datetime=now,
            instance_arn=instance_arn,
            identity_store_id=identity_store_id,
            account_name=exec_account_name,
            account_id=exec_account_id,
            accounts=accounts_table,
            users=users_table,
            groups=groups_table,
            group_memberships=group_memberships_table,
            permission_sets=permission_sets_table,
            assignments=assignments_table
        )

        # Save report to file
        file_path = f'output/inventory_{now}.md'
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(report)
        logging.info(f'Inventory report saved to {file_path}')


def main():
    inventory = IdentityCenterInventory()
    inventory.generate_report()


if __name__ == '__main__':
    main()
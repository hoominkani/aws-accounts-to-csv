import logging
from datetime import datetime
from itertools import product
from operator import itemgetter
from typing import Dict, List, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError
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

    def fetch_paged_data(self, client, method: str, **kwargs) -> List[Dict]:
        """
        Fetches paginated data for a given client method.

        Args:
            client: Boto3 client.
            method (str): Method name to call on the client.
            kwargs: Additional arguments for the method.

        Returns:
            List[Dict]: A list of combined paginated results.
        """
        try:
            paginator = client.get_paginator(method)
            data = []
            for page in paginator.paginate(**kwargs):
                data.extend(page[next(iter(page))])
            return data
        except (BotoCoreError, ClientError) as e:
            logging.error(f"Error fetching paginated data: {e}")
            return []

    def fetch_accounts(self) -> None:
        """Fetch AWS accounts from AWS Organizations."""
        logging.info('Fetching AWS accounts...')
        accounts = self.fetch_paged_data(self.org_client, 'list_accounts')
        self.account_id_to_name = {account['Id']: account['Name'] for account in accounts}
        logging.info(f'Number of accounts: {len(self.account_id_to_name)}')

    def fetch_users(self, identity_store_id: str) -> None:
        """Fetch users from the Identity Store."""
        logging.info('Fetching users...')
        users = self.fetch_paged_data(self.idstore_client, 'list_users', IdentityStoreId=identity_store_id)
        self.user_id_to_name = {user['UserId']: user['DisplayName'] for user in users}
        logging.info(f'Number of users: {len(self.user_id_to_name)}')

    def fetch_groups(self, identity_store_id: str) -> None:
        """Fetch groups from the Identity Store."""
        logging.info('Fetching groups...')
        groups = self.fetch_paged_data(self.idstore_client, 'list_groups', IdentityStoreId=identity_store_id)
        self.group_id_to_name = {group['GroupId']: group['DisplayName'] for group in groups}
        logging.info(f'Number of groups: {len(self.group_id_to_name)}')

    def fetch_permission_sets(self, instance_arn: str) -> None:
        """Fetch permission sets from the IAM Identity Center instance."""
        logging.info('Fetching permission sets...')
        permission_set_arns = self.fetch_paged_data(self.ssoadmin_client, 'list_permission_sets', InstanceArn=instance_arn)
        for arn in permission_set_arns:
            try:
                permission_set = self.ssoadmin_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=arn
                )['PermissionSet']
                self.permission_sets.append(permission_set)
                self.permission_set_arn_to_name[arn] = permission_set['Name']
            except (BotoCoreError, ClientError) as e:
                logging.error(f"Error fetching permission set details for {arn}: {e}")
        logging.info(f'Number of permission sets: {len(self.permission_set_arn_to_name)}')

    def fetch_group_memberships(self, identity_store_id: str) -> List[Tuple[str, str]]:
        """Fetch group memberships from the Identity Store."""
        logging.info('Fetching group memberships...')
        memberships = []
        for group_id, group_name in self.group_id_to_name.items():
            group_memberships = self.fetch_paged_data(
                self.idstore_client, 'list_group_memberships',
                IdentityStoreId=identity_store_id, GroupId=group_id
            )
            for membership in group_memberships:
                user_id = membership['MemberId']['UserId']
                user_name = self.user_id_to_name.get(user_id, f'#DELETED({user_id})')
                memberships.append((group_name, user_name))
        logging.info(f'Number of group memberships: {len(memberships)}')
        return memberships

    def fetch_assignments(self, instance_arn: str) -> List[Tuple[str, str, str, str]]:
        """Fetch account assignments."""
        logging.info('Fetching account assignments...')
        assignments = []
        for account_id, permission_set_arn in product(self.account_id_to_name.keys(), self.permission_set_arn_to_name.keys()):
            account_name = self.account_id_to_name[account_id]
            permission_set_name = self.permission_set_arn_to_name[permission_set_arn]
            logging.info(f'Fetching assignments for {account_name}, {permission_set_name}...')
            assignments_data = self.fetch_paged_data(
                self.ssoadmin_client, 'list_account_assignments',
                InstanceArn=instance_arn, AccountId=account_id, PermissionSetArn=permission_set_arn
            )
            for assignment in assignments_data:
                principal_type = assignment['PrincipalType']
                principal_id = assignment['PrincipalId']
                principal_name = (
                    self.user_id_to_name.get(principal_id, f'#DELETED({principal_id})')
                    if principal_type == 'USER' else
                    self.group_id_to_name.get(principal_id, f'#DELETED({principal_id})')
                )
                assignments.append((account_name, principal_type, principal_name, permission_set_name))
        logging.info(f'Number of assignments: {len(assignments)}')
        return assignments

    def generate_report(self) -> None:
        """Generate the inventory report and save it to a file."""
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        logging.info('Generating inventory report...')
        self.fetch_accounts()
        exec_account_id = self.sts_client.get_caller_identity()['Account']
        exec_account_name = self.account_id_to_name.get(exec_account_id, 'Unknown')
        instances = self.ssoadmin_client.list_instances()['Instances']
        if not instances:
            logging.error('No IAM Identity Center instance found.')
            return
        instance_arn = instances[0]['InstanceArn']
        identity_store_id = instances[0]['IdentityStoreId']
        self.fetch_users(identity_store_id)
        self.fetch_groups(identity_store_id)
        self.fetch_permission_sets(instance_arn)
        group_memberships = self.fetch_group_memberships(identity_store_id)
        assignments = self.fetch_assignments(instance_arn)
        report = TEMPLATE.format(
            datetime=now,
            instance_arn=instance_arn,
            identity_store_id=identity_store_id,
            account_name=exec_account_name,
            account_id=exec_account_id,
            accounts=self.create_table(self.account_id_to_name.items(), ['Account Name', 'Account ID']),
            users=self.create_table(self.user_id_to_name.items(), ['User Name', 'User ID']),
            groups=self.create_table(self.group_id_to_name.items(), ['Group Name', 'Group ID']),
            group_memberships=self.create_table(group_memberships, ['Group Name', 'User Name']),
            permission_sets=self.create_table(self.permission_set_arn_to_name.items(), ['Permission Set Name', 'Permission Set ARN']),
            assignments=self.create_table(assignments, ['Account Name', 'Principal Type', 'Principal Name', 'Permission Set Name'])
        )
        file_path = f'output/inventory_{now}.md'
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(report)
        logging.info(f'Inventory report saved to {file_path}')

    def create_table(self, data, headers):
        """Create a table from data."""
        return tabulate(data, headers=headers, tablefmt='github')


def main():
    inventory = IdentityCenterInventory()
    inventory.generate_report()


if __name__ == '__main__':
    main()

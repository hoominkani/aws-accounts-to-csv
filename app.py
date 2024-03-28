import boto3
import logging
from datetime import datetime
import csv

logging.basicConfig(level=logging.INFO)

def create_ou_dict(client, parent_id, parent_name, prefix=''):
    """Creates a dictionary of OUs recursively based on the specified parent ID."""
    ou_path = f'{prefix}/{parent_name}'.strip('/')
    ou_dict = {parent_id: ou_path}
    response = client.list_organizational_units_for_parent(ParentId=parent_id)
    for ou in response.get('OrganizationalUnits', []):
        ou_dict.update(create_ou_dict(client, ou.get('Id'), ou.get('Name'), ou_path))
    return ou_dict

def get_org_root(client):
    """Retrieves the root ID of the organization."""
    response = client.list_roots()
    return response.get('Roots', [{}])[0].get('Id')

def get_accounts_for_parent(client, parent_id):
    """Gets AWS account information associated with the specified parent ID."""
    response = client.list_accounts_for_parent(ParentId=parent_id)
    return response.get('Accounts', [])

def generate_accounts_csv(client, ou_dict, file_path):
    """Outputs AWS account information to a CSV file"""
    accounts = []
    for ou_id, ou_path in ou_dict.items():
        logging.info(f'## searching accounts in {ou_path}...')
        for account in get_accounts_for_parent(client, ou_id):
            accounts.append([
                account.get('Name'), account.get('Id'),
                ou_path, ou_id,
                account.get('Email'), account.get('Status'),
                account.get('JoinedMethod'),
                account.get('JoinedTimestamp').strftime('%Y/%m/%d %H:%M:%S')
            ])
    accounts.sort(key=lambda x: (x[0], x[2]))

    header = ['Name', 'Id', 'OU Path', 'OU ID', 'Email', 'Status', 'JoinedMethod', 'JoinedTimestamp']
    with open(file_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
        writer.writerows([header] + accounts)

def main():
    client = boto3.client('organizations')
    datetime_now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    file_path = f'./output/accounts_{datetime_now}.csv'
    logging.info(f'[start] timestamp: {datetime_now}')

    logging.info('# getting OU dictionary...')
    ou_dict = create_ou_dict(client, get_org_root(client), 'root')
    logging.info(f'-> number of OUs: {len(ou_dict)}')

    logging.info('# creating AWS accounts list and generating CSV...')
    generate_accounts_csv(client, ou_dict, file_path)

    logging.info('[end]')

if __name__ == '__main__':
    main()
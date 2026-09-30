"""Mongo collection loaders, Vault URL, and client factory."""
from src.persistence._shared import *  # noqa: F401,F403
from src.persistence.mongo_client import get_sync_client, resolve_mongo_url


class MongoCollectionsMixin:
    def load_collection_qdrant(self):
        """Return the auth/MTC collection used by Qdrant sync workflows."""
        client = get_sync_client()
        return client[self.mtc_user_data_db_name][self.auth_mtc_collection]

    def load_auth_collection(self):
        """Return the license-auth collection."""
        client = get_sync_client()
        return client[self.mtc_user_data_db_name][self.license_auth_collection]

    def load_vault_url(self) -> str:
        return resolve_mongo_url()

    def load_collection(self):
        """Return the primary MTC collection."""
        client = get_sync_client()
        return client[self.mtc_user_data_db_name][self.mtc_collection]

    def load_collection_for_user_prompt(self, license_id):
        """Return the user-prompt collection scoped to *license_id*."""
        client = get_sync_client()
        return client[license_id][self.user_prompt_collection]

    def load_collection_for_mtc_to_atc(self, license_id):
        """Return the MTC-to-ATC bridge collection scoped to *license_id*."""
        client = get_sync_client()
        return client[license_id]["user_mtc_to_atc"]

    def load_collection_for_user_prompt_details(self, license_id):
        """Return the prompt-details collection scoped to *license_id*."""
        client = get_sync_client()
        return client[license_id][self.user_prompt_details_collection]

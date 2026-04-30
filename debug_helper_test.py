
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lango_core.settings')
django.setup()

from integrations.models import PartnerAccount, PartnerAccountTrackerIdentifier, Tracker, ApiAuthID, ApiAuthType
from integrations.utils import get_partner_tracker_identifiers

def test_helper():
    print("--- Setting up Test Data ---")
    # Clean up (optional, or use unique names)
    prefix = "test_helper_"
    
    tracker1, _ = Tracker.objects.get_or_create(name=f"{prefix}binom_1")
    tracker2, _ = Tracker.objects.get_or_create(name=f"{prefix}binom_2")
    
    auth_type, _ = ApiAuthType.objects.get_or_create(name=f"{prefix}basic")
    
    auth1, _ = ApiAuthID.objects.get_or_create(
        account_name=f"{prefix}auth1", 
        tracker=tracker1,
        auth_type=auth_type,
        defaults={'request_url': 'http://test'}
    )
    auth2, _ = ApiAuthID.objects.get_or_create(
        account_name=f"{prefix}auth2", 
        tracker=tracker2,
        auth_type=auth_type,
        defaults={'request_url': 'http://test'}
    )
    
    partner, _ = PartnerAccount.objects.get_or_create(name=f"{prefix}partner")
    
    # Identifiers
    id1, _ = PartnerAccountTrackerIdentifier.objects.update_or_create(
        partner_account=partner,
        api_auth_id=auth1,
        defaults={'account_id_in_tracker': 'ID_100'}
    )
    id2, _ = PartnerAccountTrackerIdentifier.objects.update_or_create(
        partner_account=partner,
        api_auth_id=auth2,
        defaults={'account_id_in_tracker': 'ID_200'}
    )
    
    print(f"Created Partner {partner} with IDs: {id1}, {id2}")
    
    print("\n--- Testing get_partner_tracker_identifiers ---")
    
    # 1. Test with Auth Context (Exact Match)
    res1 = get_partner_tracker_identifiers(partner, auth1)
    print(f"Auth1 Context: Expected ID_100, Got: {res1.account_id_in_tracker if res1 else 'None'}")
    assert res1.account_id_in_tracker == 'ID_100'
    
    # Verify Name Access
    res1.account_name_in_tracker = "Test Name 123"
    print(f"Accessing Name: {res1.account_name_in_tracker}")
    assert res1.account_name_in_tracker == "Test Name 123"

    # 2. Test with Tracker Context (Tracker object)
    res2 = get_partner_tracker_identifiers(partner, tracker2)
    print(f"Tracker2 Context: Expected ID_200, Got: {res2.account_id_in_tracker if res2 else 'None'}")
    assert res2.account_id_in_tracker == 'ID_200'
    
    # 3. Test with None
    res3 = get_partner_tracker_identifiers(partner, None)
    print(f"None Context: Expected First (ID_100 or 200), Got: {res3.account_id_in_tracker if res3 else 'None'}")
    assert res3 is not None
    
    print("\nSUCCESS: All tests passed.")

if __name__ == "__main__":
    test_helper()

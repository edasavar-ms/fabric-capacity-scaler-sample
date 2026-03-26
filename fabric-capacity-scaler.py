# Fabric Notebook: Auto-Scale Capacity
#
# Purpose: Scale Fabric capacity from F4 -> F8 during peak windows (7am-6pm AEST):
#            - Every Monday
#            - Tuesday of the first trading week of each month
#          and back to F4 outside those windows.
#
# "First trading week" = Mon-Fri of the week starting on the first Monday of the month.
#
# Configuration:
#   - Subscription: <your-subscription-id>
#   - Resource Group: <your-resource-group>
#   - Capacity Name: <your-capacity-name>
#   - Base SKU: F4
#   - Peak SKU: F8
#   - Schedule: See above (Australia/Sydney timezone)
#
# Authentication:
#   - Method: Service Principal + Azure Key Vault
#   - Credentials (Tenant ID, Client ID, Client Secret) are stored in Azure Key Vault
#   - Retrieved at runtime via mssparkutils.credentials.getSecret()
#   - The Fabric Pipeline Notebook activity must be configured to run as the
#     Service Principal (Settings > Connection > Service Principal)
#
# Usage:
#   - Schedule this notebook in a Fabric Pipeline with two triggers per peak day:
#     1. 7am AEST  -> runs with parameter action="scale_up"
#     2. 6pm AEST  -> runs with parameter action="scale_down"
#   - Or use action="auto" on a single trigger and let the notebook decide
#   - Or run manually with action="scale_up" / "scale_down" / "check_status"

# ============================================================
# Cell 1: Configuration
# ============================================================

# Notebook parameters (set these or override via Pipeline)
action = "check_status"  # Options: "scale_up", "scale_down", "check_status", "auto"

# Azure Resource Details
SUBSCRIPTION_ID = "<your-subscription-id>"
RESOURCE_GROUP  = "<your-resource-group>"
CAPACITY_NAME   = "<your-capacity-name>"

# SKU Configuration
BASE_SKU = "F4"
PEAK_SKU = "F8"

# Schedule Configuration (for "auto" mode)
# Peak windows (7am-6pm AEST):
#   - Every Monday
#   - Tuesday of the first trading week of the month
#     (first trading week = Mon-Fri of the week starting on the first Monday of the month)
PEAK_START_HOUR = 7   # 7am AEST
PEAK_END_HOUR   = 18  # 6pm AEST
TIMEZONE        = "Australia/Sydney"

# ARM API
API_VERSION  = "2023-11-01"
ARM_BASE_URL = f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.Fabric/capacities/{CAPACITY_NAME}"

# ============================================================
# Key Vault Configuration
# Credentials for the Service Principal are stored in Key Vault.
# The Service Principal must be assigned:
#   - Contributor on the Fabric Capacity resource (for ARM API access)
#   - Key Vault Secrets User on the Key Vault (to read secrets below)
# ============================================================
KEY_VAULT_URL        = "https://<your-keyvault-name>.vault.azure.net/"
SECRET_TENANT_ID     = "fabric-scaler-tenant-id"
SECRET_CLIENT_ID     = "fabric-scaler-client-id"
SECRET_CLIENT_SECRET = "fabric-scaler-client-secret"

print("Configuration loaded:")
print(f"  Capacity: {CAPACITY_NAME}")
print(f"  Base SKU: {BASE_SKU} | Peak SKU: {PEAK_SKU}")
print(f"  Action: {action}")
print(f"  Auth: Service Principal via Key Vault ({KEY_VAULT_URL})")

# ============================================================
# Cell 2: Helper Functions
# ============================================================

# %pip install msal  # Uncomment and run once if msal is not available in your environment

import msal
import requests
import json
import time
from datetime import datetime, timedelta
import pytz


def get_arm_token():
    """Get Azure ARM access token using Service Principal credentials from Key Vault."""
    # Retrieve credentials securely from Key Vault - nothing is hardcoded
    tenant_id     = mssparkutils.credentials.getSecret(KEY_VAULT_URL, SECRET_TENANT_ID)
    client_id     = mssparkutils.credentials.getSecret(KEY_VAULT_URL, SECRET_CLIENT_ID)
    client_secret = mssparkutils.credentials.getSecret(KEY_VAULT_URL, SECRET_CLIENT_SECRET)

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret
    )
    result = app.acquire_token_for_client(scopes=["https://management.azure.com/.default"])

    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception(f"ARM token acquisition failed: {result.get('error_description', result.get('error', 'Unknown error'))}")


def get_headers():
    """Build request headers with ARM token."""
    return {
        "Authorization": f"Bearer {get_arm_token()}",
        "Content-Type": "application/json"
    }


def get_capacity_status():
    """Get current capacity SKU and state."""
    url = f"{ARM_BASE_URL}?api-version={API_VERSION}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    data = response.json()

    return {
        "sku":      data.get("sku", {}).get("name", "Unknown"),
        "state":    data.get("properties", {}).get("state", "Unknown"),
        "location": data.get("location", "Unknown")
    }


def scale_capacity(target_sku):
    """Scale the Fabric capacity to the target SKU."""
    url     = f"{ARM_BASE_URL}?api-version={API_VERSION}"
    payload = {"sku": {"name": target_sku, "tier": "Fabric"}}

    response = requests.patch(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json() if response.text else {"status": "accepted", "code": response.status_code}


def verify_scale(target_sku, wait_seconds=30):
    """Wait briefly and confirm the capacity has reached the target SKU."""
    print(f"  Waiting {wait_seconds}s for scale operation to complete...")
    time.sleep(wait_seconds)
    new_status = get_capacity_status()
    print(f"  New SKU: {new_status['sku']} | State: {new_status['state']}")
    if new_status["sku"] == target_sku:
        print(f"  ✅ Successfully scaled to {target_sku}!")
    else:
        print(f"  ⏳ Scaling in progress. Current: {new_status['sku']}. Check again shortly.")


def is_first_trading_week_of_month():
    """Return True if today falls within the first trading week of the current month.

    Definition: the Mon-Fri week starting on the first Monday of the month.
    Example: if March 1 is a Sunday, first trading week = Mon Mar 2 – Fri Mar 6.
    """
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # days_to_monday: 0 if the 1st is already Monday, otherwise days until next Monday
    days_to_monday = (7 - first_of_month.weekday()) % 7
    first_monday   = first_of_month + timedelta(days=days_to_monday)
    first_friday   = first_monday + timedelta(days=4)

    return first_monday.date() <= now.date() <= first_friday.date()


def is_peak_time():
    """Check if current time is within a peak window (7am-6pm AEST) on a peak day.

    Peak days:
      - Every Monday
      - Tuesday of the first trading week of the month
    """
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    is_monday              = now.weekday() == 0
    is_tuesday             = now.weekday() == 1
    in_first_trading_week  = is_first_trading_week_of_month()
    is_peak_day            = is_monday or (is_tuesday and in_first_trading_week)
    is_peak_hours          = PEAK_START_HOUR <= now.hour < PEAK_END_HOUR

    print(f"  Current time: {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    print(f"  Monday: {is_monday} | Tuesday in first trading week: {is_tuesday and in_first_trading_week}")
    print(f"  Peak day: {is_peak_day}")
    print(f"  Peak hours ({PEAK_START_HOUR}:00-{PEAK_END_HOUR}:00): {is_peak_hours}")

    return is_peak_day and is_peak_hours


print("Helper functions loaded.")

# ============================================================
# Cell 3: Execute Action
# ============================================================

print("=" * 60)
print("FABRIC CAPACITY SCALER")
print("=" * 60)

# Step 1: Get current status
print("\n📊 Current Capacity Status:")
status = get_capacity_status()
print(f"  SKU: {status['sku']}")
print(f"  State: {status['state']}")
print(f"  Location: {status['location']}")

# Step 2: Resolve "auto" to an explicit action based on schedule
if action == "auto":
    print("\n🤖 Auto mode - checking schedule...")
    if is_peak_time():
        action = "scale_up"
        print(f"  -> Peak time detected. Will scale UP to {PEAK_SKU}")
    else:
        action = "scale_down"
        print(f"  -> Off-peak. Will scale DOWN to {BASE_SKU}")

# Step 3: Execute
if action == "scale_up":
    target = PEAK_SKU
    if status["sku"] == target:
        print(f"\n✅ Already at {target}. No change needed.")
    else:
        print(f"\n⬆️  Scaling UP: {status['sku']} -> {target}...")
        result = scale_capacity(target)
        print(f"  Result: {json.dumps(result, indent=2)}")
        verify_scale(target)

elif action == "scale_down":
    target = BASE_SKU
    if status["sku"] == target:
        print(f"\n✅ Already at {target}. No change needed.")
    else:
        print(f"\n⬇️  Scaling DOWN: {status['sku']} -> {target}...")
        result = scale_capacity(target)
        print(f"  Result: {json.dumps(result, indent=2)}")
        verify_scale(target)

elif action == "check_status":
    print("\nℹ️  Status check complete. No scaling performed.")
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    print(f"  Current time: {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    print(f"  Is peak time: {is_peak_time()}")

else:
    print(f"\n❌ Unknown action: '{action}'. Use: scale_up, scale_down, check_status, auto")

print("\n" + "=" * 60)
print("Done.")

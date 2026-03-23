# Fabric Capacity Scaler

A Microsoft Fabric notebook that automatically scales your Fabric capacity up or down on a schedule, using a Service Principal for authentication. Credentials are stored securely in Azure Key Vault — nothing is hardcoded.

---

> [!IMPORTANT]
> **This is a sample repository.** The notebook file contains placeholder values that you **must** replace with your own Azure resource details before running.
>
> In `fabric-capacity-scaler.py`, update the following variables in **Cell 1**:
>
> | Variable | Description | Example |
> |----------|-------------|---------|
> | `SUBSCRIPTION_ID` | Your Azure subscription ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
> | `RESOURCE_GROUP` | Resource group containing your Fabric capacity | `my-resource-group` |
> | `CAPACITY_NAME` | The name of your Fabric capacity resource | `my-fabric-capacity` |
> | `KEY_VAULT_URL` | Full URL of your Azure Key Vault | `https://my-keyvault.vault.azure.net/` |
>
> All other values (SKUs, schedule, timezone) are pre-configured with sensible defaults and can be adjusted to suit your requirements.

---

## What it does

| Action | Description |
|--------|-------------|
| `scale_up` | Scales the capacity to the peak SKU (e.g. F4 → F8) |
| `scale_down` | Scales the capacity back to the base SKU (e.g. F8 → F4) |
| `check_status` | Reports the current SKU and state — no changes made |
| `auto` | Checks the current time and automatically picks `scale_up` or `scale_down` based on the configured schedule |

The default configuration scales up on **Monday mornings at 7am AEST** and back down at **6pm AEST**, but all schedule and SKU values are easily configurable at the top of the notebook.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Microsoft Fabric capacity | Must be an F-SKU capacity (F2 and above) |
| Azure Key Vault | To store Service Principal credentials |
| Service Principal | Registered in Entra ID with the permissions below |
| `msal` Python package | Pre-installed in most Fabric environments; see note in Cell 2 if not available |

### Service Principal permissions required

- **Contributor** on the Fabric Capacity resource (allows ARM API scaling calls)
- **Key Vault Secrets User** on the Azure Key Vault (allows reading credentials at runtime)

---

## Setup

### 1. Store credentials in Key Vault

Add three secrets to your Azure Key Vault:

| Secret name | Value |
|-------------|-------|
| `fabric-scaler-tenant-id` | Your Entra ID tenant ID |
| `fabric-scaler-client-id` | The Service Principal's client (application) ID |
| `fabric-scaler-client-secret` | The Service Principal's client secret |

You can use different secret names — just update the `SECRET_*` constants in Cell 1 to match.

### 2. Update Cell 1 configuration

Open `fabric-capacity-scaler.py` (or paste it into a Fabric notebook) and update the values in **Cell 1**:

```python
SUBSCRIPTION_ID = "<your-subscription-id>"
RESOURCE_GROUP  = "<your-resource-group>"
CAPACITY_NAME   = "<your-capacity-name>"

BASE_SKU = "F4"   # SKU to use outside peak hours
PEAK_SKU = "F8"   # SKU to use during peak hours

KEY_VAULT_URL = "https://<your-keyvault-name>.vault.azure.net/"
```

### 3. Configure the Fabric Pipeline

1. Create a Fabric Pipeline and add a **Notebook activity** pointing to this notebook.
2. In the activity settings, go to **Settings → Connection** and set it to run as your **Service Principal**.
3. Add a pipeline parameter named `action` and pass it as a notebook parameter.
4. Set up two scheduled triggers:
   - **Monday 7am AEST** → pipeline parameter `action = "scale_up"`
   - **Monday 6pm AEST** → pipeline parameter `action = "scale_down"`

Alternatively, use `action = "auto"` on a single trigger and let the notebook determine the correct action based on the current time.

---

## Running manually

Set the `action` variable in Cell 1 before running the notebook:

```python
action = "check_status"  # Safe default — no changes made
action = "scale_up"      # Force scale to peak SKU
action = "scale_down"    # Force scale to base SKU
action = "auto"          # Let the schedule logic decide
```

---

## Notes

- After a scale operation, the notebook waits **30 seconds** and checks the new status. Fabric capacity scaling can occasionally take longer — if the status still shows the old SKU, wait a minute and run `check_status` to confirm.
- The `auto` mode uses the server's local time converted to the configured timezone (`Australia/Sydney` by default). If deploying in a different region, verify the timezone setting.
- This notebook uses the **Azure ARM REST API** directly (`management.azure.com`) — no Azure SDK installation required beyond `msal`.

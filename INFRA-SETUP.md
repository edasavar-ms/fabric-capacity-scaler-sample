# Infrastructure Setup Guide

This guide covers everything the infrastructure team needs to configure before the Fabric Capacity Scaler notebook can run. Once complete, hand the Key Vault URL and capacity details to the team deploying the notebook.

---

## Overview

The notebook authenticates using a **Service Principal** (an app identity in Entra ID) rather than a user account. At runtime, the notebook fetches the Service Principal's credentials from **Azure Key Vault** — nothing is stored in the notebook itself.

The Service Principal needs two permissions:
1. **Contributor** on the Fabric Capacity resource — to call the scale API
2. **Key Vault Secrets User** on the Key Vault — to read its own credentials at runtime

---

## Step 1 — Register the Service Principal in Entra ID

1. Go to the [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations**
2. Click **New registration**
3. Fill in:
   - **Name:** `fabric-capacity-scaler` (or follow your org's naming convention)
   - **Supported account types:** Single tenant
   - **Redirect URI:** Leave blank
4. Click **Register**
5. On the app overview page, copy and save:
   - **Application (client) ID**
   - **Directory (tenant) ID**

### Create a client secret

1. In the app registration, go to **Certificates & secrets** → **Client secrets**
2. Click **New client secret**
3. Set a description (e.g. `fabric-scaler-secret`) and an expiry (12 or 24 months recommended)
4. Click **Add**
5. **Copy the secret value immediately** — it is only shown once

> **Security note:** Store the secret value directly in Key Vault (Step 3). Do not paste it into any file, email, or Teams message.

---

## Step 2 — Assign the Contributor role on the Fabric Capacity

1. In the Azure Portal, navigate to your **Microsoft Fabric capacity** resource
2. Go to **Access control (IAM)** → **Add** → **Add role assignment**
3. Select the **Contributor** role → click **Next**
4. Under **Members**, choose **User, group, or service principal**
5. Search for the app name created in Step 1 (e.g. `fabric-capacity-scaler`) → select it
6. Click **Review + assign**

---

## Step 3 — Create the Azure Key Vault (if one doesn't exist)

> Skip this step if you are adding secrets to an existing Key Vault.

1. In the Azure Portal, go to **Key vaults** → **Create**
2. Fill in:
   - **Subscription / Resource group:** Use the same ones as the Fabric capacity
   - **Key vault name:** e.g. `kv-fabric-scaler` (must be globally unique)
   - **Region:** Same region as your Fabric capacity
   - **Pricing tier:** Standard
3. On the **Access configuration** tab, select **Azure role-based access control (RBAC)**
4. Click **Review + create** → **Create**
5. Copy and save the **Vault URI** (format: `https://<keyvault-name>.vault.azure.net/`)

---

## Step 4 — Store the Service Principal credentials as secrets

1. In the Azure Portal, open your Key Vault → **Secrets** → **Generate/Import**
2. Create the following three secrets (one at a time):

| Secret name | Value to paste |
|-------------|---------------|
| `fabric-scaler-tenant-id` | Directory (tenant) ID from Step 1 |
| `fabric-scaler-client-id` | Application (client) ID from Step 1 |
| `fabric-scaler-client-secret` | Client secret value from Step 1 |

   For each secret:
   - **Upload options:** Manual
   - **Name:** Exactly as shown in the table above
   - **Value:** Paste the corresponding value
   - Leave all other fields as default → click **Create**

---

## Step 5 — Grant the Service Principal access to read secrets

The Service Principal needs permission to read its own credentials from Key Vault at runtime.

1. In the Key Vault, go to **Access control (IAM)** → **Add** → **Add role assignment**
2. Select the **Key Vault Secrets User** role → click **Next**
3. Under **Members**, choose **User, group, or service principal**
4. Search for `fabric-capacity-scaler` → select it
5. Click **Review + assign**

---

## Step 6 — Collect details for the notebook team

Once the above steps are complete, provide the following to the team deploying the notebook:

| Item | Where to find it |
|------|-----------------|
| Azure Subscription ID | Azure Portal → Subscriptions |
| Resource Group name | Azure Portal → the Fabric capacity resource |
| Fabric Capacity name | Azure Portal → the Fabric capacity resource |
| Key Vault URI | Azure Portal → Key Vault → Overview (`https://<name>.vault.azure.net/`) |

The secret names are fixed (`fabric-scaler-tenant-id`, `fabric-scaler-client-id`, `fabric-scaler-client-secret`) — the notebook team does not need the raw credential values.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `AuthenticationError` at runtime | Client secret expired or incorrect | Rotate the secret in Entra ID and update the Key Vault secret value |
| `403 Forbidden` on scale API call | Contributor role not assigned (or assigned at wrong scope) | Verify role assignment is on the Fabric capacity resource, not the subscription or resource group |
| `Access denied` reading Key Vault secret | Key Vault Secrets User role not assigned to the Service Principal | Re-check Step 5 — ensure the correct app is selected |
| Secret not found in Key Vault | Secret name mismatch | Confirm secret names exactly match the table in Step 4 (case-sensitive) |

---

## Secret rotation

Client secrets expire. Set a calendar reminder before the expiry date to:

1. Create a **new** client secret in Entra ID (do not delete the old one yet)
2. Update the `fabric-scaler-client-secret` value in Key Vault with the new secret
3. Verify the notebook runs successfully
4. Delete the old secret from Entra ID

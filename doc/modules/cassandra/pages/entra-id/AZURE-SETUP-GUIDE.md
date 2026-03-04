# Microsoft Entra ID Setup Guide for Apache Cassandra
## Azure Configuration for Customers

This guide walks you through setting up Microsoft Entra ID (formerly Azure Active Directory)
to authenticate and authorize users connecting to Apache Cassandra.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Step 1: Register an Application in Entra ID](#step-1-register-an-application-in-entra-id)
3. [Step 2: Configure API Permissions](#step-2-configure-api-permissions)
4. [Step 3: Create App Roles (Optional)](#step-3-create-app-roles-optional)
5. [Step 4: Configure Group Claims](#step-4-configure-group-claims)
6. [Step 5: Create Client Credentials](#step-5-create-client-credentials)
7. [Step 6: Assign Users and Groups](#step-6-assign-users-and-groups)
8. [Step 7: Configure Cassandra Server](#step-7-configure-cassandra-server)
9. [Step 8: Create Cassandra Roles](#step-8-create-cassandra-roles)
10. [Step 9: Set Up Group-to-Role Mappings](#step-9-set-up-group-to-role-mappings)
11. [Step 10: Configure Client Applications](#step-10-configure-client-applications)
12. [Managed Identity Setup (Azure VMs/AKS)](#managed-identity-setup)
13. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

- An **Azure subscription** with access to Microsoft Entra ID
- **Global Administrator** or **Application Administrator** role in your Entra ID tenant
- A running **Apache Cassandra 4.1+** cluster with the Entra ID authenticator patch applied
- **Azure CLI** installed (optional, for CLI-based setup)

**Information you'll need to collect:**

| Item | Where to find it | Format |
|------|-------------------|--------|
| Tenant ID | Azure Portal → Entra ID → Overview | UUID (e.g., `a1b2c3d4-e5f6-7890-abcd-ef1234567890`) |
| Client ID | Created in Step 1 | UUID |
| Client Secret | Created in Step 5 | String |
| Group Object IDs | Azure Portal → Entra ID → Groups | UUID per group |

---

## Step 1: Register an Application in Entra ID

An **App Registration** represents your Cassandra cluster in Entra ID. All tokens are issued
for this application's audience.

### Using Azure Portal

1. Navigate to **Azure Portal** → **Microsoft Entra ID** → **App registrations**
2. Click **+ New registration**
3. Fill in the details:

   | Field | Value |
   |-------|-------|
   | **Name** | `Apache Cassandra Cluster` (or your preferred name) |
   | **Supported account types** | `Accounts in this organizational directory only` (Single tenant) |
   | **Redirect URI** | Leave blank (not needed for client credentials) |

4. Click **Register**
5. On the Overview page, note the following values:

   ```
   Application (client) ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  ← This is your client_id
   Directory (tenant) ID:   xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  ← This is your tenant_id
   ```

### Using Azure CLI

```bash
# Login to Azure
az login

# Create the app registration
az ad app create \
  --display-name "Apache Cassandra Cluster" \
  --sign-in-audience "AzureADMyOrg"

# Note the appId (client_id) from the output
# Get your tenant ID
az account show --query tenantId -o tsv
```

---

## Step 2: Configure API Permissions

The app registration needs to expose an API so that client applications can request tokens.

### Using Azure Portal

1. Go to your app registration → **Expose an API**
2. Click **Set** next to "Application ID URI"
3. Accept the default URI: `api://{client-id}` or set a custom one
4. Click **Save**

This creates the scope `api://{client-id}/.default` which is what clients will request.

### Using Azure CLI

```bash
# Set the Application ID URI
az ad app update \
  --id YOUR_CLIENT_ID \
  --identifier-uris "api://YOUR_CLIENT_ID"
```

---

## Step 3: Create App Roles (Optional)

App Roles provide a way to define named roles (like "CassandraReader", "CassandraWriter")
that are included in the JWT's `roles` claim. This is an **alternative** to using group-based
authorization.

### Using Azure Portal

1. Go to your app registration → **App roles**
2. Click **+ Create app role**
3. Create roles for your Cassandra access patterns:

   | Display name | Value | Description | Allowed member types |
   |-------------|-------|-------------|---------------------|
   | Cassandra Reader | `CassandraReader` | Read-only access to Cassandra | Users/Groups + Applications |
   | Cassandra Writer | `CassandraWriter` | Read-write access to Cassandra | Users/Groups + Applications |
   | Cassandra Admin | `CassandraAdmin` | Full administrative access | Users/Groups + Applications |

4. Click **Apply** for each role

### Using Azure CLI

```bash
# Get the current app manifest
az ad app show --id YOUR_CLIENT_ID --query appRoles

# Update app roles (replace with your desired roles)
az ad app update --id YOUR_CLIENT_ID --app-roles '[
  {
    "allowedMemberTypes": ["User", "Application"],
    "description": "Read-only access to Cassandra",
    "displayName": "Cassandra Reader",
    "isEnabled": true,
    "value": "CassandraReader"
  },
  {
    "allowedMemberTypes": ["User", "Application"],
    "description": "Read-write access to Cassandra",
    "displayName": "Cassandra Writer",
    "isEnabled": true,
    "value": "CassandraWriter"
  },
  {
    "allowedMemberTypes": ["User", "Application"],
    "description": "Full administrative access",
    "displayName": "Cassandra Admin",
    "isEnabled": true,
    "value": "CassandraAdmin"
  }
]'
```

---

## Step 4: Configure Group Claims

To use Entra ID security groups for authorization, you need to enable group claims in the token.

### Using Azure Portal

1. Go to your app registration → **Token configuration**
2. Click **+ Add groups claim**
3. Select the group types to include:

   | Option | Recommendation |
   |--------|---------------|
   | **Security groups** | ✅ Recommended — select this |
   | **Directory roles** | Optional — for admin roles |
   | **Groups assigned to the application** | ✅ Recommended if you have > 200 groups |
   | **All groups** | Use only for small tenants |

4. Under **Customize token properties by type**:
   - For **Access tokens**: Select **Group ID** (Object IDs of groups)
5. Click **Add**

> **Important**: If a user belongs to more than ~200 groups, Entra ID returns a `_claim_names`
> and `_claim_sources` overage indicator instead of all groups. For large organizations, use
> "Groups assigned to the application" to limit which groups are included.

### Using Azure CLI

```bash
# Enable group claims in the token
az ad app update --id YOUR_CLIENT_ID \
  --optional-claims '{
    "accessToken": [{
      "name": "groups",
      "additionalProperties": ["emit_as_roles"]
    }]
  }'
```

---

## Step 5: Create Client Credentials

Client applications need credentials to authenticate with Entra ID. Create **one or more**
of the following depending on your use case.

### Option A: Client Secret (for service-to-service)

1. Go to your app registration → **Certificates & secrets**
2. Click **+ New client secret**
3. Set a description (e.g., "Cassandra App Secret") and expiration
4. Click **Add**
5. **Copy the secret value immediately** — it's only shown once!

```
Secret ID:    xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Secret Value: Abc123~xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ← Save this securely
Expires:      2027-03-03
```

### Option B: Certificate (more secure, for production)

1. Generate a certificate:
   ```bash
   openssl req -x509 -newkey rsa:2048 -keyout cassandra-auth.key \
     -out cassandra-auth.crt -days 365 -nodes \
     -subj "/CN=CassandraAuth"
   ```

2. Upload the certificate's `.crt` file in **Certificates & secrets** → **Certificates**

### Option C: Managed Identity (for Azure VMs/AKS)

No client secret needed — see [Managed Identity Setup](#managed-identity-setup) below.

---

## Step 6: Assign Users and Groups

Users and groups must be **assigned** to the application to get tokens.

### Create Security Groups

1. Navigate to **Entra ID** → **Groups** → **+ New group**
2. Create groups matching your access patterns:

   | Group Name | Type | Description |
   |-----------|------|-------------|
   | `Cassandra-Readers` | Security | Users with read access |
   | `Cassandra-Writers` | Security | Users with read/write access |
   | `Cassandra-Admins` | Security | Database administrators |

3. Add members to each group
4. **Note the Object ID** of each group (visible on the group overview page)

### Assign Users/Groups to the Application

1. Go to **Entra ID** → **Enterprise applications** → find your app (same name)
2. Click **Users and groups** → **+ Add user/group**
3. Select users or groups and assign them an App Role (if configured)

> Without Enterprise Application assignment, users may still get tokens but without
> app role claims. Group claims will still be included if configured in Step 4.

### Using Azure CLI

```bash
# Get the Enterprise Application's service principal object ID
SP_ID=$(az ad sp list --filter "appId eq 'YOUR_CLIENT_ID'" --query "[0].id" -o tsv)

# Assign a user to the application
az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignments" \
  --body '{
    "principalId": "USER_OBJECT_ID",
    "resourceId": "'$SP_ID'",
    "appRoleId": "APP_ROLE_ID"
  }'
```

---

## Step 7: Configure Cassandra Server

### Edit cassandra.yaml

```yaml
# Change authenticator from PasswordAuthenticator to EntraIdAuthenticator
authenticator: org.apache.cassandra.auth.EntraIdAuthenticator

# Change authorizer from CassandraAuthorizer to EntraIdAuthorizer
authorizer: org.apache.cassandra.auth.EntraIdAuthorizer

# Role manager stays the same
role_manager: CassandraRoleManager

# Add your Entra ID configuration
entra_tenant_id: YOUR-TENANT-ID-HERE
entra_client_id: YOUR-CLIENT-ID-HERE
```

### Enable TLS (Strongly Recommended)

Since JWT tokens are sent over the wire, enable client-to-node encryption:

```yaml
client_encryption_options:
    enabled: true
    optional: false
    keystore: /etc/cassandra/certs/keystore.jks
    keystore_password: changeit
    # Optionally require client certificates:
    # require_client_auth: true
    # truststore: /etc/cassandra/certs/truststore.jks
    # truststore_password: changeit
```

### Restart Cassandra

Perform a rolling restart of your cluster:

```bash
# On each node
nodetool drain
sudo systemctl restart cassandra
```

---

## Step 8: Create Cassandra Roles

Create Cassandra roles that match the Entra ID principal names (email addresses or UPNs).

**Connect using the default superuser first** (or use a migration approach):

```sql
-- Create roles for individual users
CREATE ROLE 'user1@contoso.com' WITH LOGIN = true;
CREATE ROLE 'user2@contoso.com' WITH LOGIN = true;

-- Create roles for group-based permissions (no login needed)
CREATE ROLE db_readers;
CREATE ROLE db_writers;
CREATE ROLE db_admins WITH SUPERUSER = true;

-- Grant permissions to group roles
GRANT SELECT ON KEYSPACE my_keyspace TO db_readers;
GRANT SELECT, MODIFY ON KEYSPACE my_keyspace TO db_writers;
GRANT ALL ON ALL KEYSPACES TO db_admins;
```

> **Note**: When a user authenticates with Entra ID, their principal name (typically
> `preferred_username` or `upn` from the JWT) is used as the Cassandra role name.
> This role must exist with `LOGIN = true`.

---

## Step 9: Set Up Group-to-Role Mappings

Map Entra ID group Object IDs to Cassandra roles:

```sql
-- Map the "Cassandra-Readers" Entra ID group to the "db_readers" Cassandra role
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'db_readers');

-- Map the "Cassandra-Writers" group to "db_writers"
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'db_writers');

-- Map the "Cassandra-Admins" group to "db_admins"
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'db_admins');

-- If using App Roles instead of groups:
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('CassandraReader', 'db_readers');

INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('CassandraWriter', 'db_writers');

INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('CassandraAdmin', 'db_admins');
```

### Verify Mappings

```sql
SELECT * FROM system_auth.entra_group_roles;
```

Expected output:
```
 group_id                              | cassandra_role
---------------------------------------+----------------
 a1b2c3d4-e5f6-7890-abcd-ef1234567890 |     db_readers
 b2c3d4e5-f6a7-8901-bcde-f12345678901 |     db_writers
 c3d4e5f6-a7b8-9012-cdef-123456789012 |      db_admins
                       CassandraReader |     db_readers
                       CassandraWriter |     db_writers
                        CassandraAdmin |      db_admins
```

---

## Step 10: Configure Client Applications

See the [Connection Examples](./CONNECTION-EXAMPLES.md) document for per-language setup, or
the quick start below:

### Quick Start — Java

```java
EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .tenantId("your-tenant-id")
    .clientId("your-client-id")
    .clientSecret("your-client-secret")
    .build();

Cluster cluster = Cluster.builder()
    .addContactPoint("cassandra-host")
    .withAuthProvider(authProvider)
    .withSSL()  // Always use TLS!
    .build();
```

### Quick Start — Python/CQLSH

```python
from cqlshlib.entra_id_auth_provider import EntraIdAuthProvider
from cassandra.cluster import Cluster

auth = EntraIdAuthProvider(
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    client_secret='your-secret'
)
cluster = Cluster(['cassandra-host'], auth_provider=auth)
```

---

## Managed Identity Setup

For applications running on Azure infrastructure (VMs, App Service, AKS, Azure Functions),
use **Managed Identity** to avoid managing client secrets entirely.

### Step 1: Enable Managed Identity

**For Azure VMs:**
```bash
az vm identity assign --name myVM --resource-group myRG
```

**For Azure Kubernetes Service (AKS):**
```bash
az aks update --name myCluster --resource-group myRG --enable-managed-identity
```

**For Azure App Service:**
```bash
az webapp identity assign --name myApp --resource-group myRG
```

### Step 2: Get the Managed Identity's Client ID

```bash
# For system-assigned identity
IDENTITY_CLIENT_ID=$(az vm show --name myVM --resource-group myRG \
  --query identity.principalId -o tsv)

# For user-assigned identity
IDENTITY_CLIENT_ID=$(az identity show --name myIdentity --resource-group myRG \
  --query clientId -o tsv)
```

### Step 3: Assign the Managed Identity to the App Registration

```bash
SP_ID=$(az ad sp list --filter "appId eq 'YOUR_CASSANDRA_CLIENT_ID'" --query "[0].id" -o tsv)

az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_ID/appRoleAssignments" \
  --body '{
    "principalId": "'$IDENTITY_CLIENT_ID'",
    "resourceId": "'$SP_ID'",
    "appRoleId": "APP_ROLE_ID_FOR_DESIRED_ACCESS"
  }'
```

### Step 4: Create Cassandra Role for the Managed Identity

```sql
-- Use the managed identity's Object ID or client ID as the role name
CREATE ROLE 'MANAGED_IDENTITY_OBJECT_ID' WITH LOGIN = true;
GRANT SELECT, MODIFY ON KEYSPACE my_keyspace TO 'MANAGED_IDENTITY_OBJECT_ID';
```

### Step 5: Use in Application Code

**Java:**
```java
EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .tenantId("your-tenant-id")
    .clientId("your-client-id")
    .useManagedIdentity(true)
    .build();
```

**C#:**
```csharp
var authProvider = EntraIdAuthProvider.WithManagedIdentity(
    tenantId: "your-tenant-id",
    clientId: "your-client-id"
);
```

**Python:**
```python
auth = EntraIdAuthProvider(
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    use_managed_identity=True
)
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `Invalid token audience` | Token's `aud` doesn't match `entra_client_id` | Verify `entra_client_id` in cassandra.yaml matches the App Registration's client ID. Ensure the token scope uses `api://{client-id}/.default` |
| `Invalid token issuer` | Token's `iss` doesn't match expected tenant | Verify `entra_tenant_id` in cassandra.yaml matches your Entra ID tenant ID |
| `Token has expired` | JWT `exp` is in the past | Check clock synchronization (NTP) on Cassandra nodes. Tokens typically expire after 1 hour |
| `Unable to find signing key` | JWKS cache doesn't have the signing key | This resolves itself as the cache refreshes. May indicate network issues reaching login.microsoftonline.com |
| `AADSTS700016: Application not found` | Client ID is incorrect or app was deleted | Verify the App Registration exists in Entra ID |
| `AADSTS7000215: Invalid client secret` | Client secret is wrong or expired | Rotate the client secret in Entra ID |
| `Role 'user@contoso.com' doesn't exist` | Cassandra role not created for the user | Create the role: `CREATE ROLE 'user@contoso.com' WITH LOGIN = true;` |
| Groups not in token | Groups claim not configured | Follow Step 4 to configure group claims |
| Too many groups, `_claim_sources` in token | User has > 200 groups | Use "Groups assigned to the application" in token configuration |

### Diagnostic Commands

```bash
# Test token acquisition (Azure CLI)
az account get-access-token \
  --resource api://YOUR_CLIENT_ID \
  --tenant YOUR_TENANT_ID

# Decode a JWT token (paste at jwt.ms or use command line)
echo "YOUR_JWT_TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool

# Check Cassandra logs for auth errors
grep -i "entra\|authentication\|token" /var/log/cassandra/system.log | tail -20

# Verify group-role mappings
cqlsh -e "SELECT * FROM system_auth.entra_group_roles;"

# Check if a role exists
cqlsh -e "SELECT role, can_login FROM system_auth.roles WHERE role = 'user@contoso.com';"
```

### Verify Entra ID Configuration

Run this script to validate your setup:

```bash
#!/bin/bash
TENANT_ID="your-tenant-id"
CLIENT_ID="your-client-id"

echo "=== Checking JWKS Endpoint ==="
curl -s "https://login.microsoftonline.com/$TENANT_ID/discovery/v2.0/keys" | python3 -m json.tool | head -20

echo ""
echo "=== Checking OpenID Configuration ==="
curl -s "https://login.microsoftonline.com/$TENANT_ID/v2.0/.well-known/openid-configuration" | python3 -m json.tool

echo ""
echo "=== Checking App Registration ==="
az ad app show --id $CLIENT_ID --query '{appId: appId, displayName: displayName, identifierUris: identifierUris}' -o table
```

---

## Security Checklist

Before going to production, verify:

- [ ] TLS enabled for client-to-node connections (`client_encryption_options.enabled: true`)
- [ ] TLS enabled for inter-node connections (`server_encryption_options.internode_encryption: all`)
- [ ] Client secrets stored securely (Key Vault, not in code/config files)
- [ ] Cassandra nodes can reach `login.microsoftonline.com` on port 443
- [ ] Clock synchronization (NTP) configured on all Cassandra nodes
- [ ] Group-role mappings reviewed and minimal (principle of least privilege)
- [ ] App Registration configured with "Accounts in this organizational directory only"
- [ ] Client secret expiration monitoring in place
- [ ] Cassandra audit logging enabled if required by compliance
- [ ] Managed Identity used where possible (avoids secret management)

# Entra ID Authentication — Connection Examples

Complete, copy-paste-ready code examples for connecting to Apache Cassandra using
Microsoft Entra ID authentication across all supported drivers and CQLSH.

---

## Table of Contents

1. [Java Driver 3.x Examples](#1-java-driver-3x-examples)
2. [Java Driver 4.x Examples](#2-java-driver-4x-examples)
3. [C# Driver Examples](#3-c-driver-examples)
4. [Python Driver Examples](#4-python-driver-examples)
5. [CQLSH Examples](#5-cqlsh-examples)
6. [SSL/TLS Configuration](#6-ssltls-configuration)
7. [Connection Pooling & Retry](#7-connection-pooling--retry)
8. [Environment Variable Patterns](#8-environment-variable-patterns)
9. [Docker & Kubernetes Patterns](#9-docker--kubernetes-patterns)

---

## 1. Java Driver 3.x Examples

### 1.1 Project Setup

**Option A — Pre-Built Plugin (Recommended):**

Use the pre-built `cassandra-entra-id-auth-driver3` JAR. This is an uber JAR that bundles
MSAL4J with relocated packages to avoid classpath conflicts.

```xml
<dependency>
    <groupId>org.apache.cassandra</groupId>
    <artifactId>cassandra-entra-id-auth-driver3</artifactId>
    <version>1.0.0</version>
</dependency>
```

**Gradle:**
```gradle
implementation 'org.apache.cassandra:cassandra-entra-id-auth-driver3:1.0.0'
```

The uber JAR (`cassandra-entra-id-auth-driver3-1.0.0-all.jar`) is also available for
non-Maven projects — just add it to your classpath alongside the DataStax driver.

To build the plugin from source, see `driver-plugins/java/README.md`.

**Option B — Manual Dependencies:**

If you prefer to manage dependencies yourself:

```xml
<dependencies>
    <dependency>
        <groupId>com.datastax.cassandra</groupId>
        <artifactId>cassandra-driver-core</artifactId>
        <version>3.11.3</version>
    </dependency>
    <dependency>
        <groupId>com.microsoft.azure</groupId>
        <artifactId>msal4j</artifactId>
        <version>1.14.0</version>
    </dependency>
</dependencies>
```

### 1.2 Service Principal (Client Credentials)

```java
import com.datastax.driver.core.Cluster;
import com.datastax.driver.core.Row;
import com.datastax.driver.core.Session;

public class ServicePrincipalExample {
    public static void main(String[] args) {
        // Build auth provider with service principal credentials
        EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
            .tenantId(System.getenv("ENTRA_TENANT_ID"))
            .clientId(System.getenv("ENTRA_CLIENT_ID"))
            .clientSecret(System.getenv("ENTRA_CLIENT_SECRET"))
            .build();

        // Connect to Cassandra
        try (Cluster cluster = Cluster.builder()
                .addContactPoint("cassandra-host")
                .withPort(9042)
                .withAuthProvider(authProvider)
                .build()) {

            Session session = cluster.connect();

            // Execute a query
            for (Row row : session.execute("SELECT keyspace_name FROM system_schema.keyspaces")) {
                System.out.println("Keyspace: " + row.getString("keyspace_name"));
            }
        }
    }
}
```

### 1.3 Username/Password (ROPC)

```java
EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .tenantId("your-tenant-id")
    .clientId("your-client-id")
    .username("alice@contoso.com")
    .password("P@ssw0rd!")
    .build();

Cluster cluster = Cluster.builder()
    .addContactPoint("cassandra-host")
    .withAuthProvider(authProvider)
    .build();
```

### 1.4 Managed Identity (Azure VM / AKS)

```java
EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .clientId("your-client-id")
    .useManagedIdentity(true)     // uses VM/pod assigned identity
    .build();

Cluster cluster = Cluster.builder()
    .addContactPoint("cassandra-host")
    .withAuthProvider(authProvider)
    .build();
```

### 1.5 Custom Scope / Authority

```java
EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .tenantId("your-tenant-id")
    .clientId("your-client-id")
    .clientSecret("your-secret")
    .scope("api://custom-api-id/.default")
    .authority("https://login.microsoftonline.com/your-tenant-id")
    .build();
```

---

## 2. Java Driver 4.x Examples

### 2.1 Project Setup

**Option A — Pre-Built Plugin (Recommended):**

```xml
<dependency>
    <groupId>org.apache.cassandra</groupId>
    <artifactId>cassandra-entra-id-auth-driver4</artifactId>
    <version>1.0.0</version>
</dependency>
```

**Gradle:**
```gradle
implementation 'org.apache.cassandra:cassandra-entra-id-auth-driver4:1.0.0'
```

**Option B — Manual Dependencies:**

```xml
<dependencies>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-core</artifactId>
        <version>4.17.0</version>
    </dependency>
    <dependency>
        <groupId>com.microsoft.azure</groupId>
        <artifactId>msal4j</artifactId>
        <version>1.14.0</version>
    </dependency>
</dependencies>
```

### 2.2 Service Principal

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;

public class ServicePrincipalV4Example {
    public static void main(String[] args) {
        EntraIdAuthProviderV4 authProvider = EntraIdAuthProviderV4.builder()
            .tenantId(System.getenv("ENTRA_TENANT_ID"))
            .clientId(System.getenv("ENTRA_CLIENT_ID"))
            .clientSecret(System.getenv("ENTRA_CLIENT_SECRET"))
            .build();

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("cassandra-host", 9042))
                .withLocalDatacenter("datacenter1")
                .withAuthProvider(authProvider)
                .build()) {

            ResultSet rs = session.execute("SELECT release_version FROM system.local");
            Row row = rs.one();
            System.out.println("Version: " + row.getString("release_version"));
        }
    }
}
```

### 2.3 Managed Identity

```java
EntraIdAuthProviderV4 authProvider = EntraIdAuthProviderV4.builder()
    .clientId(System.getenv("ENTRA_CLIENT_ID"))
    .useManagedIdentity(true)
    .build();

CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("cassandra-host", 9042))
    .withLocalDatacenter("datacenter1")
    .withAuthProvider(authProvider)
    .build();
```

### 2.4 application.conf Integration

```hocon
# src/main/resources/application.conf
datastax-java-driver {
  basic {
    contact-points = ["cassandra-host:9042"]
    load-balancing-policy.local-datacenter = datacenter1
  }
  advanced {
    auth-provider {
      # Use programmatic auth provider (see code below)
      class = ""
    }
  }
}
```

```java
// Programmatic override (auth-provider.class must be empty or unset)
CqlSession session = CqlSession.builder()
    .withAuthProvider(EntraIdAuthProviderV4.builder()
        .tenantId(System.getenv("ENTRA_TENANT_ID"))
        .clientId(System.getenv("ENTRA_CLIENT_ID"))
        .clientSecret(System.getenv("ENTRA_CLIENT_SECRET"))
        .build())
    .build();  // contact points from application.conf
```

---

## 3. C# Driver Examples

### 3.1 Project Setup

**Option A — Pre-Built NuGet Package (Recommended):**

```bash
dotnet add package Cassandra.Auth.EntraId
```

This pulls in `CassandraCSharpDriver`, `Microsoft.Identity.Client`, and `Azure.Identity`
transitively. To build the package from source, see `driver-plugins/csharp/README.md`.

**Option B — Manual Dependencies:**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="CassandraCSharpDriver" Version="3.19.5" />
    <PackageReference Include="Microsoft.Identity.Client" Version="4.56.0" />
    <PackageReference Include="Azure.Identity" Version="1.10.2" />
  </ItemGroup>
</Project>
```

### 3.2 Service Principal

```csharp
using Cassandra;
using System;

class Program
{
    static void Main()
    {
        var authProvider = new EntraIdAuthProvider(
            tenantId: Environment.GetEnvironmentVariable("ENTRA_TENANT_ID"),
            clientId: Environment.GetEnvironmentVariable("ENTRA_CLIENT_ID"),
            clientSecret: Environment.GetEnvironmentVariable("ENTRA_CLIENT_SECRET")
        );

        var cluster = Cluster.Builder()
            .AddContactPoint("cassandra-host")
            .WithPort(9042)
            .WithAuthProvider(authProvider)
            .Build();

        var session = cluster.Connect();
        var rs = session.Execute("SELECT release_version FROM system.local");
        foreach (var row in rs)
        {
            Console.WriteLine($"Version: {row.GetValue<string>("release_version")}");
        }
    }
}
```

### 3.3 Username/Password (ROPC)

```csharp
var authProvider = new EntraIdAuthProvider(
    tenantId: "your-tenant-id",
    clientId: "your-client-id",
    username: "alice@contoso.com",
    password: "P@ssw0rd!"
);
```

### 3.4 Managed Identity

```csharp
var authProvider = EntraIdAuthProvider.WithManagedIdentity(
    clientId: Environment.GetEnvironmentVariable("ENTRA_CLIENT_ID")
);

var cluster = Cluster.Builder()
    .AddContactPoint("cassandra-host")
    .WithAuthProvider(authProvider)
    .Build();
```

### 3.5 Default Azure Credential

```csharp
// Works with: az login, Visual Studio, Managed Identity, environment variables
var authProvider = EntraIdAuthProvider.WithDefaultCredential(
    clientId: Environment.GetEnvironmentVariable("ENTRA_CLIENT_ID")
);
```

### 3.6 ASP.NET Dependency Injection

```csharp
// Program.cs
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddSingleton<ICluster>(sp =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    var authProvider = new EntraIdAuthProvider(
        config["Entra:TenantId"]!,
        config["Entra:ClientId"]!,
        config["Entra:ClientSecret"]!
    );
    return Cluster.Builder()
        .AddContactPoint(config["Cassandra:Host"]!)
        .WithAuthProvider(authProvider)
        .Build();
});

builder.Services.AddScoped<ISession>(sp =>
    sp.GetRequiredService<ICluster>().Connect()
);
```

---

## 4. Python Driver Examples

### 4.1 Install Dependencies

**Option A — Pre-Built pip Package (Recommended):**

```bash
pip install cassandra-entra-id-auth          # core (cassandra-driver + msal)
pip install cassandra-entra-id-auth[azure]    # adds azure-identity for DefaultAzureCredential
pip install cassandra-entra-id-auth[all]      # all optional dependencies
```

To build the package from source, see `driver-plugins/python/README.md`.

**Option B — Manual Dependencies:**

```bash
pip install cassandra-driver msal azure-identity
```

### 4.2 Service Principal

```python
from cassandra.cluster import Cluster
from cassandra_entra_id_auth import EntraIdAuthProvider
import os

auth_provider = EntraIdAuthProvider(
    tenant_id=os.environ['ENTRA_TENANT_ID'],
    client_id=os.environ['ENTRA_CLIENT_ID'],
    client_secret=os.environ['ENTRA_CLIENT_SECRET'],
)

cluster = Cluster(
    contact_points=['cassandra-host'],
    port=9042,
    auth_provider=auth_provider,
)
session = cluster.connect()

rows = session.execute("SELECT keyspace_name FROM system_schema.keyspaces")
for row in rows:
    print(f"Keyspace: {row.keyspace_name}")
```

### 4.3 Username/Password (ROPC)

```python
auth_provider = EntraIdAuthProvider(
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    username='alice@contoso.com',
    password='P@ssw0rd!',
)
```

### 4.4 Managed Identity

```python
auth_provider = EntraIdAuthProvider(
    client_id='your-client-id',
    use_managed_identity=True,
)
```

### 4.5 Default Azure Credential

```python
auth_provider = EntraIdAuthProvider(
    client_id='your-client-id',
    use_default_credential=True,
)
```

### 4.6 Pre-Acquired Token

```python
import msal

# Acquire token yourself
app = msal.ConfidentialClientApplication(
    client_id='your-client-id',
    authority='https://login.microsoftonline.com/your-tenant-id',
    client_credential='your-secret',
)
result = app.acquire_token_for_client(scopes=['api://your-client-id/.default'])
jwt = result['access_token']

# Pass it directly
auth_provider = EntraIdAuthProvider(
    client_id='your-client-id',
    token=jwt,
)
```

### 4.7 With SSL/TLS

```python
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
import ssl

ssl_context = ssl.create_default_context(cafile='/path/to/ca-cert.pem')
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

auth_provider = EntraIdAuthProvider(
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    client_secret='your-secret',
)

cluster = Cluster(
    contact_points=['cassandra-host'],
    port=9042,
    auth_provider=auth_provider,
    ssl_context=ssl_context,
    load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'),
)
session = cluster.connect()
```

### 4.8 Async (aiohttp / asyncio)

```python
from cassandra.cluster import Cluster
from cassandra.io.asyncioreactor import AsyncioConnection

auth_provider = EntraIdAuthProvider(
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    client_secret='your-secret',
)

cluster = Cluster(
    contact_points=['cassandra-host'],
    auth_provider=auth_provider,
    connection_class=AsyncioConnection,
)
session = cluster.connect()

# Use execute_async
future = session.execute_async("SELECT * FROM system.local")
rows = future.result()
```

---

## 5. CQLSH Examples

### 5.1 Service Principal via cqlshrc

**~/.cassandra/cqlshrc:**
```ini
[connection]
hostname = cassandra-host
port = 9042

[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
tenant_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_secret = your-client-secret-value
```

```bash
cqlsh
```

### 5.2 Managed Identity via cqlshrc

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
use_managed_identity = true
```

### 5.3 Default Credential via cqlshrc

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
use_default_credential = true
```

### 5.4 With SSL

**~/.cassandra/cqlshrc:**
```ini
[connection]
hostname = cassandra-host
port = 9042
factory = cqlshlib.ssl.ssl_transport_factory

[ssl]
certfile = /path/to/ca-cert.pem
validate = true

[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
tenant_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_secret = your-secret
```

```bash
cqlsh --ssl
```

### 5.5 CQLSH with Separate Credentials File

**~/.cassandra/cqlshrc:**
```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider

[credentials]
credentials_file = /home/user/.cassandra/credentials
```

**~/.cassandra/credentials:**
```ini
[entra_id_auth_provider.EntraIdAuthProvider]
tenant_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_secret = your-secret
```

---

## 6. SSL/TLS Configuration

> **Important**: Always enable SSL/TLS in production. SASL PLAIN transmits the JWT token
> in cleartext without transport encryption.

### 6.1 Java (Both Driver Versions)

```java
// Using JDK SSL
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.security.KeyStore;
import java.io.FileInputStream;

KeyStore trustStore = KeyStore.getInstance("JKS");
try (FileInputStream fis = new FileInputStream("/path/to/truststore.jks")) {
    trustStore.load(fis, "truststorepassword".toCharArray());
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);

// Driver 3.x
Cluster cluster = Cluster.builder()
    .addContactPoint("cassandra-host")
    .withSSL(JdkSSLOptions.builder().withSSLContext(sslContext).build())
    .withAuthProvider(authProvider)
    .build();

// Driver 4.x — configure in application.conf
// datastax-java-driver.advanced.ssl-engine-factory.class = DefaultSslEngineFactory
// datastax-java-driver.advanced.ssl-engine-factory.truststore-path = /path/to/truststore.jks
// datastax-java-driver.advanced.ssl-engine-factory.truststore-password = "truststorepassword"
```

### 6.2 C#

```csharp
var sslOptions = new SSLOptions()
    .SetRemoteCertValidationCallback((sender, cert, chain, errors) =>
    {
        // In production, validate the certificate properly
        return errors == System.Net.Security.SslPolicyErrors.None;
    });

var cluster = Cluster.Builder()
    .AddContactPoint("cassandra-host")
    .WithSSL(sslOptions)
    .WithAuthProvider(authProvider)
    .Build();
```

### 6.3 Python

```python
import ssl

ssl_context = ssl.create_default_context(cafile='/path/to/ca-cert.pem')
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

cluster = Cluster(
    contact_points=['cassandra-host'],
    auth_provider=auth_provider,
    ssl_context=ssl_context,
)
```

---

## 7. Connection Pooling & Retry

### 7.1 Java 3.x — Pool Configuration

```java
PoolingOptions pooling = new PoolingOptions()
    .setConnectionsPerHost(HostDistance.LOCAL, 2, 4)
    .setConnectionsPerHost(HostDistance.REMOTE, 1, 2)
    .setMaxRequestsPerConnection(HostDistance.LOCAL, 32768)
    .setHeartbeatIntervalSeconds(30);

Cluster cluster = Cluster.builder()
    .addContactPoint("cassandra-host")
    .withPoolingOptions(pooling)
    .withAuthProvider(authProvider)
    .build();
```

### 7.2 Java 4.x — Retry on Auth Failure

```java
// application.conf
// datastax-java-driver.advanced.reconnection-policy {
//   class = ExponentialReconnectionPolicy
//   base-delay = 1 second
//   max-delay = 60 seconds
// }
```

### 7.3 Python — Retry Policy

```python
from cassandra.policies import ExponentialReconnectionPolicy

cluster = Cluster(
    contact_points=['cassandra-host'],
    auth_provider=auth_provider,
    reconnection_policy=ExponentialReconnectionPolicy(
        base_delay=1.0, max_delay=60.0
    ),
)
```

---

## 8. Environment Variable Patterns

### 8.1 Standard Environment Variables

All examples above use these environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `ENTRA_TENANT_ID` | Azure AD Tenant ID | `a1b2c3d4-...` |
| `ENTRA_CLIENT_ID` | App Registration Client ID | `e5f6a7b8-...` |
| `ENTRA_CLIENT_SECRET` | Client Secret | `abc~def...` |
| `ENTRA_USERNAME` | User principal name (ROPC) | `alice@contoso.com` |
| `ENTRA_PASSWORD` | User password (ROPC) | `P@ssw0rd!` |
| `CASSANDRA_HOST` | Cassandra contact point | `cassandra-host` |
| `CASSANDRA_PORT` | Cassandra native port | `9042` |

### 8.2 .env File

```bash
# .env
ENTRA_TENANT_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
ENTRA_CLIENT_ID=e5f6a7b8-c9d0-1234-5678-abcdef012345
ENTRA_CLIENT_SECRET=abc~defGHI123_jklMNO456
CASSANDRA_HOST=10.0.1.100
CASSANDRA_PORT=9042
```

### 8.3 Azure Key Vault Integration (Java)

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

SecretClient secretClient = new SecretClientBuilder()
    .vaultUrl("https://my-vault.vault.azure.net")
    .credential(new DefaultAzureCredentialBuilder().build())
    .buildClient();

String clientSecret = secretClient.getSecret("cassandra-client-secret").getValue();

EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .tenantId(System.getenv("ENTRA_TENANT_ID"))
    .clientId(System.getenv("ENTRA_CLIENT_ID"))
    .clientSecret(clientSecret)
    .build();
```

---

## 9. Docker & Kubernetes Patterns

### 9.1 Docker Compose — Service Principal

```yaml
version: '3.8'
services:
  app:
    image: my-app:latest
    environment:
      - ENTRA_TENANT_ID=${ENTRA_TENANT_ID}
      - ENTRA_CLIENT_ID=${ENTRA_CLIENT_ID}
      - ENTRA_CLIENT_SECRET=${ENTRA_CLIENT_SECRET}
      - CASSANDRA_HOST=cassandra
    depends_on:
      - cassandra

  cassandra:
    image: cassandra:4.1
    volumes:
      - ./conf/cassandra.yaml:/etc/cassandra/cassandra.yaml
    environment:
      - JVM_OPTS=-Dcassandra.entra.tenant_id=${ENTRA_TENANT_ID} -Dcassandra.entra.client_id=${ENTRA_CLIENT_ID}
```

### 9.2 Kubernetes — Managed Identity (Azure Workload Identity)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cassandra-client-sa
  annotations:
    azure.workload.identity/client-id: "your-client-id"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cassandra-client
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: cassandra-client-sa
      containers:
      - name: app
        image: my-app:latest
        env:
        - name: ENTRA_CLIENT_ID
          value: "your-client-id"
        - name: CASSANDRA_HOST
          value: "cassandra-headless.cassandra.svc.cluster.local"
```

### 9.3 Kubernetes — Secret-Based

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: entra-credentials
type: Opaque
stringData:
  tenant-id: "your-tenant-id"
  client-id: "your-client-id"
  client-secret: "your-client-secret"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cassandra-client
spec:
  template:
    spec:
      containers:
      - name: app
        image: my-app:latest
        env:
        - name: ENTRA_TENANT_ID
          valueFrom:
            secretKeyRef:
              name: entra-credentials
              key: tenant-id
        - name: ENTRA_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: entra-credentials
              key: client-id
        - name: ENTRA_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: entra-credentials
              key: client-secret
```

---

## Summary of All Auth Provider Classes

| Language | Package / Artifact | Class | Install |
|----------|-------------------|-------|--------|
| Java 3.x | `org.apache.cassandra:cassandra-entra-id-auth-driver3` | `org.apache.cassandra.auth.entra.EntraIdAuthProvider` | Maven / uber JAR |
| Java 4.x | `org.apache.cassandra:cassandra-entra-id-auth-driver4` | `org.apache.cassandra.auth.entra.EntraIdAuthProviderV4` | Maven / uber JAR |
| C# | `Cassandra.Auth.EntraId` (NuGet) | `Cassandra.Auth.EntraId.EntraIdAuthProvider` | `dotnet add package` |
| Python | `cassandra-entra-id-auth` (pip) | `cassandra_entra_id_auth.EntraIdAuthProvider` | `pip install` |
| CQLSH | Ships with Cassandra | `cqlshlib.entra_id_auth_provider.EntraIdAuthProvider` | Built-in |

> **Example source files** are also available in `examples/entra-id/` for reference.
> The `driver-plugins/` directory contains full build projects for producing the above artifacts.

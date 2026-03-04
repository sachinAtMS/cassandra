#!/usr/bin/env python3
"""
Generate a comprehensive PDF document about
Microsoft Entra ID Authentication for Apache Cassandra.

Uses fpdf2 for PDF generation — no external tools required.

Output:
    Cassandra_EntraID_Auth.pdf   (same directory)
"""

from fpdf import FPDF
import os

# ── Brand colours (RGB tuples) ─────────────────────────────────
AZURE_BLUE   = (0, 120, 212)
DARK_BLUE    = (0, 43, 92)
MID_BLUE     = (0, 99, 177)
LIGHT_BLUE   = (222, 236, 249)
ACCENT_GREEN = (16, 124, 16)
ACCENT_ORANGE= (255, 140, 0)
ACCENT_RED   = (209, 52, 56)
WHITE        = (255, 255, 255)
BLACK        = (0, 0, 0)
GRAY         = (96, 96, 96)
LIGHT_GRAY   = (242, 242, 242)
TEAL         = (30, 136, 168)
CODE_BG      = (30, 30, 46)
CODE_FG      = (166, 226, 46)


class EntraIdPDF(FPDF):
    """Custom PDF with headers, footers, and helper methods."""

    def __init__(self):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=20)
        self.page_w = 210
        self.margin = 15
        self.content_w = self.page_w - 2 * self.margin

    def header(self):
        if self.page_no() == 1:
            return  # title page has custom header
        self.set_fill_color(*DARK_BLUE)
        self.rect(0, 0, 210, 12, 'F')
        self.set_fill_color(*AZURE_BLUE)
        self.rect(0, 12, 210, 1, 'F')
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(*WHITE)
        self.set_xy(10, 3)
        self.cell(0, 6, 'Microsoft Entra ID Authentication for Apache Cassandra', 0, 0, 'L')
        self.set_xy(150, 3)
        self.cell(0, 6, 'Confidential', 0, 0, 'R')
        self.set_text_color(*BLACK)
        self.ln(16)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(*GRAY)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'C')

    def title_page(self):
        self.add_page()
        # Full-page dark background
        self.set_fill_color(*DARK_BLUE)
        self.rect(0, 0, 210, 297, 'F')

        # Title
        self.set_text_color(*WHITE)
        self.set_font('Helvetica', 'B', 28)
        self.set_y(60)
        self.multi_cell(0, 14, 'Microsoft Entra ID\nAuthentication & Authorization\nfor Apache Cassandra', 0, 'L')

        # Subtitle
        self.ln(5)
        self.set_font('Helvetica', '', 16)
        self.set_text_color(*LIGHT_BLUE)
        self.cell(0, 10, 'Enterprise-Grade Identity Integration for Cassandra Service Providers', 0, 1, 'L')

        # Accent line
        self.ln(3)
        self.set_fill_color(*AZURE_BLUE)
        self.rect(self.margin, self.get_y(), 50, 1.5, 'F')
        self.ln(10)

        # Meta
        self.set_font('Helvetica', '', 12)
        self.set_text_color(*WHITE)
        self.cell(0, 8, 'Sachin Gupta  |  March 2026', 0, 1, 'L')
        self.cell(0, 8, 'Apache Cassandra 4.1.x', 0, 1, 'L')
        self.cell(0, 8, 'Draft - v1.0', 0, 1, 'L')

        # Feature box
        self.ln(15)
        self.set_fill_color(*AZURE_BLUE)
        self.rect(self.margin, self.get_y(), 70, 35, 'F')
        self.set_font('Helvetica', 'B', 11)
        y = self.get_y() + 5
        for line in ['JWT + MSAL Authentication', 'Zero External Dependencies', 'Plugin JAR Deployment', 'All Major Drivers Supported']:
            self.set_xy(self.margin + 5, y)
            self.cell(60, 6, line, 0, 0, 'L')
            y += 7

        self.set_text_color(*BLACK)

    def section_header(self, num, title, subtitle=None):
        """Add a numbered section header."""
        self.ln(5)
        self.set_fill_color(*DARK_BLUE)
        self.set_text_color(*WHITE)
        self.set_font('Helvetica', 'B', 16)
        self.cell(0, 10, f'  {num}. {title}', 0, 1, 'L', fill=True)
        self.set_fill_color(*AZURE_BLUE)
        self.rect(self.margin, self.get_y(), self.content_w, 0.8, 'F')
        self.ln(2)
        if subtitle:
            self.set_font('Helvetica', 'I', 10)
            self.set_text_color(*AZURE_BLUE)
            self.cell(0, 6, subtitle, 0, 1, 'L')
        self.set_text_color(*BLACK)
        self.ln(2)

    def sub_header(self, title):
        self.ln(3)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(*MID_BLUE)
        self.cell(0, 7, title, 0, 1, 'L')
        self.set_text_color(*BLACK)
        self.ln(1)

    def body_text(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*GRAY)
        self.multi_cell(0, 5.5, text, 0, 'L')
        self.set_text_color(*BLACK)
        self.ln(2)

    def bullet_list(self, items, indent=5):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*GRAY)
        for item in items:
            x = self.get_x()
            self.set_x(self.margin + indent)
            self.cell(4, 5.5, '-', 0, 0)  # bullet char
            self.multi_cell(self.content_w - indent - 6, 5.5, f' {item}', 0, 'L')
            self.ln(1)
        self.set_text_color(*BLACK)
        self.ln(2)

    def numbered_list(self, items, indent=5):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(*GRAY)
        for i, item in enumerate(items, 1):
            self.set_x(self.margin + indent)
            self.cell(8, 5.5, f'{i}.', 0, 0)
            self.multi_cell(self.content_w - indent - 10, 5.5, f' {item}', 0, 'L')
            self.ln(1)
        self.set_text_color(*BLACK)
        self.ln(2)

    def code_block(self, code, title=None):
        if title:
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(*DARK_BLUE)
            self.cell(0, 5, title, 0, 1, 'L')
            self.ln(1)
        self.set_fill_color(*CODE_BG)
        self.set_text_color(*CODE_FG)
        self.set_font('Courier', '', 8)
        # Calculate height
        lines = code.split('\n')
        h = len(lines) * 4.5 + 6
        y_start = self.get_y()
        # Check if we need a page break
        if y_start + h > 280:
            self.add_page()
            y_start = self.get_y()
        self.rect(self.margin, y_start, self.content_w, h, 'F')
        self.set_xy(self.margin + 3, y_start + 3)
        for line in lines:
            self.cell(0, 4.5, line, 0, 1)
            self.set_x(self.margin + 3)
        self.set_text_color(*BLACK)
        self.set_y(y_start + h + 3)

    def info_box(self, text, color=AZURE_BLUE):
        """Colored info callout box."""
        self.set_fill_color(color[0], color[1], color[2])
        y = self.get_y()
        self.rect(self.margin, y, 3, 12, 'F')  # left accent bar
        self.set_fill_color(color[0]//4 + 200, color[1]//4 + 200, color[2]//4 + 200)
        self.rect(self.margin + 3, y, self.content_w - 3, 12, 'F')
        self.set_xy(self.margin + 6, y + 2)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(color[0], color[1], color[2])
        self.multi_cell(self.content_w - 10, 5, text, 0, 'L')
        self.set_text_color(*BLACK)
        self.set_y(y + 14)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            n = len(headers)
            col_widths = [self.content_w / n] * n
        # Header
        self.set_fill_color(*DARK_BLUE)
        self.set_text_color(*WHITE)
        self.set_font('Helvetica', 'B', 8)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, 1, 0, 'C', fill=True)
        self.ln()
        # Rows
        self.set_font('Helvetica', '', 8)
        alt = False
        for row in rows:
            if alt:
                self.set_fill_color(*LIGHT_GRAY)
            else:
                self.set_fill_color(*WHITE)
            self.set_text_color(*BLACK)
            for i, val in enumerate(row):
                self.cell(col_widths[i], 6, val, 1, 0, 'C', fill=True)
            self.ln()
            alt = not alt
        self.set_text_color(*BLACK)
        self.ln(3)

    def diagram_box(self, label, x, y, w, h, bg=AZURE_BLUE, fg=WHITE):
        self.set_fill_color(*bg)
        self.rect(x, y, w, h, 'F')
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(*fg)
        self.set_xy(x + 1, y + h/2 - 3)
        self.cell(w - 2, 6, label, 0, 0, 'C')

    def diagram_arrow(self, x1, y1, x2, y2, label=''):
        self.set_draw_color(*AZURE_BLUE)
        self.line(x1, y1, x2, y2)
        # Arrowhead (simple)
        if label:
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            self.set_font('Helvetica', '', 7)
            self.set_text_color(*AZURE_BLUE)
            self.set_xy(mx - 10, my - 3)
            self.cell(20, 5, label, 0, 0, 'C')


# ══════════════════════════════════════════════════════════════════
# BUILD THE DOCUMENT
# ══════════════════════════════════════════════════════════════════

pdf = EntraIdPDF()
pdf.alias_nb_pages()
pdf.set_left_margin(15)
pdf.set_right_margin(15)

# ── Title Page ────────────────────────────────────────────────────
pdf.title_page()

# ── Table of Contents ─────────────────────────────────────────────
pdf.add_page()
pdf.set_font('Helvetica', 'B', 20)
pdf.set_text_color(*DARK_BLUE)
pdf.cell(0, 12, 'Table of Contents', 0, 1, 'L')
pdf.set_fill_color(*AZURE_BLUE)
pdf.rect(15, pdf.get_y(), 40, 1, 'F')
pdf.ln(5)

toc = [
    "1.  Executive Summary",
    "2.  Current Cassandra Authentication",
    "3.  Challenges with Password-Based Auth",
    "4.  Microsoft Entra ID Overview",
    "5.  Solution Architecture",
    "6.  MSAL - Microsoft Authentication Library",
    "7.  MSAL on Client Side - Token Acquisition",
    "8.  MSAL on Server Side - JWT Validation",
    "9.  Authentication Data Flow",
    "10. Authorization & Group-to-Role Mapping",
    "11. Azure Portal Setup - Complete Guide",
    "12. Server-Side Components",
    "13. Server Deployment Options",
    "14. Cassandra Configuration",
    "15. Client Driver - Java (DataStax 3.x & 4.x)",
    "16. Client Driver - C# (.NET)",
    "17. Client Driver - Python",
    "18. CQLSH Integration",
    "19. SASL Wire Format",
    "20. JWKS & Token Validation Deep Dive",
    "21. Managed Identity Deep Dive",
    "22. Security Considerations",
    "23. Backward Compatibility & Migration",
    "24. Testing Strategy",
    "25. Production Deployment Architecture",
    "26. Summary & Next Steps",
]

pdf.set_font('Helvetica', '', 11)
pdf.set_text_color(*GRAY)
for item in toc:
    pdf.cell(0, 7, item, 0, 1, 'L')
pdf.set_text_color(*BLACK)

# ══════════════════════════════════════════════════════════════════
# 1. EXECUTIVE SUMMARY
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(1, "Executive Summary")

pdf.body_text(
    "This document describes a comprehensive solution for integrating Microsoft Entra ID "
    "(formerly Azure Active Directory) authentication and authorization into Apache Cassandra 4.1.x. "
    "The solution enables enterprise-grade identity management, replacing Cassandra's native "
    "PasswordAuthenticator with JWT-based authentication powered by the Microsoft Identity Platform."
)

pdf.sub_header("Key Benefits")
pdf.bullet_list([
    "Centralized Identity Management - Users, groups, and service principals managed in Entra ID",
    "Multi-Factor Authentication (MFA) - Enforced at token issuance via Conditional Access",
    "Group-Based Authorization - Entra ID security groups mapped to Cassandra roles",
    "Managed Identity Support - Zero-secret authentication for Azure-hosted workloads",
    "Zero External Dependencies - Server-side uses only JDK crypto (java.security.Signature)",
    "Drop-In Plugin JAR - Works with stock Cassandra 4.1.x without source modification",
    "Pre-Built Driver Plugins - Maven, NuGet, pip packages for Java, C#, Python drivers",
    "CQLSH Integration - Native Entra ID support built into Cassandra's cqlsh tool",
])

pdf.sub_header("Solution Components")
pdf.table(
    ["Component", "Technology", "Deployment"],
    [
        ["Server Authenticator", "EntraIdAuthenticator (Java)", "Plugin JAR or Source"],
        ["Token Validator", "JDK SHA256withRSA", "Part of server plugin"],
        ["Authorizer", "EntraIdAuthorizer (extends CassandraAuthorizer)", "Part of server plugin"],
        ["Java Driver Plugin", "MSAL4J (shaded uber JAR)", "Maven artifact"],
        ["C# Driver Plugin", "MSAL.NET", "NuGet package"],
        ["Python Driver Plugin", "msal (Python)", "pip package"],
        ["CQLSH Module", "msal (Python)", "Ships with Cassandra"],
    ],
    [45, 60, 75]
)

# ══════════════════════════════════════════════════════════════════
# 2. CURRENT CASSANDRA AUTH
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(2, "Current Cassandra Authentication", "How PasswordAuthenticator works today")

pdf.body_text(
    "Apache Cassandra ships with PasswordAuthenticator as its built-in authentication mechanism. "
    "When a client connects, it sends a username and password via the SASL PLAIN mechanism. "
    "Cassandra computes a bcrypt hash of the password and compares it against the stored hash "
    "in the system_auth.roles table."
)

pdf.sub_header("Authentication Flow (Current)")
pdf.numbered_list([
    "Client application connects to Cassandra via the native protocol (port 9042)",
    "Cassandra responds with AUTHENTICATE challenge containing 'org.apache.cassandra.auth.PasswordAuthenticator'",
    "Client sends SASL PLAIN response: NUL + username + NUL + password",
    "PasswordAuthenticator computes bcrypt(password) and compares with system_auth.roles",
    "If matched, Cassandra creates an AuthenticatedUser and allows the connection",
])

pdf.sub_header("Authorization Flow (Current)")
pdf.body_text(
    "CassandraAuthorizer checks the system_auth.role_permissions table for each resource access. "
    "Permissions are granted per-user using GRANT statements. There is no support for "
    "group-based access control or integration with external directory services."
)

pdf.code_block(
    "-- Current: manual per-user permission grants\n"
    "CREATE ROLE db_reader WITH PASSWORD = 'secret' AND LOGIN = true;\n"
    "GRANT SELECT ON KEYSPACE production TO db_reader;\n"
    "\n"
    "-- Each user needs individual role assignment\n"
    "-- No group-based access control available",
    "Current Permission Model (CQL)"
)

# ══════════════════════════════════════════════════════════════════
# 3. CHALLENGES
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(3, "Challenges with Password-Based Authentication")

challenges = [
    ("No Centralized Identity Management",
     "Each Cassandra cluster maintains its own user database in system_auth.roles. "
     "There is no single source of truth for identities. When an employee leaves the organization, "
     "their Cassandra credentials must be manually revoked across every cluster."),
    ("No Multi-Factor Authentication",
     "Password-only authentication cannot enforce MFA or conditional access policies. "
     "This is a significant compliance gap for regulated industries (healthcare, finance)."),
    ("Credential Rotation Burden",
     "Passwords must be rotated manually across all client applications and configuration files. "
     "In a large deployment with hundreds of microservices, this becomes a major operational burden."),
    ("No Group-Based Access Control",
     "Permissions are granted to individual users. There is no mechanism to automatically "
     "map Active Directory groups to Cassandra roles, leading to permission sprawl."),
    ("Audit and Compliance Gaps",
     "Authentication events are logged locally in Cassandra's logs but not integrated with "
     "corporate SIEM systems. There is no centralized view of who accessed what data."),
    ("No Single Sign-On (SSO)",
     "Users maintain separate Cassandra credentials, disconnected from their corporate identity. "
     "This creates friction and increases the risk of weak or shared passwords."),
]

for title, desc in challenges:
    pdf.sub_header(title)
    pdf.body_text(desc)

# ══════════════════════════════════════════════════════════════════
# 4. ENTRA ID OVERVIEW
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(4, "Microsoft Entra ID Overview", "Formerly Azure Active Directory (Azure AD)")

pdf.body_text(
    "Microsoft Entra ID is Microsoft's cloud-based identity and access management service. "
    "It provides authentication and authorization for applications using industry-standard "
    "protocols (OAuth 2.0, OpenID Connect, SAML 2.0). Entra ID manages the full lifecycle "
    "of user identities, security groups, and service principals."
)

pdf.sub_header("Key Concepts")
pdf.bullet_list([
    "Tenant: Your organization's dedicated Entra ID instance (identified by tenant_id/directory_id)",
    "App Registration: Represents your application (Cassandra) in Entra ID (identified by client_id)",
    "Service Principal: The local representation of an app registration within a tenant",
    "Security Groups: Collections of users/service principals for group-based access",
    "App Roles: Application-specific roles defined in the app registration manifest",
    "JWT Access Tokens: Signed tokens issued by Entra ID containing user identity and claims",
    "JWKS (JSON Web Key Set): Public keys published by Entra ID for token signature verification",
    "Managed Identity: Azure-managed credentials for VMs, AKS, and other Azure resources",
    "Conditional Access: Policies that enforce MFA, device compliance, location restrictions",
])

pdf.sub_header("How It Works for Cassandra")
pdf.body_text(
    "1. An App Registration is created in Entra ID to represent the Cassandra cluster.\n"
    "2. Client applications use MSAL to acquire JWT access tokens from Entra ID.\n"
    "3. The JWT token is sent to Cassandra in the SASL PLAIN password field.\n"
    "4. Cassandra's EntraIdAuthenticator validates the JWT signature using JWKS public keys.\n"
    "5. Claims (groups, roles) from the JWT are extracted and used for authorization.\n"
    "6. EntraIdAuthorizer maps Entra ID groups to Cassandra roles for permission checks."
)

# ══════════════════════════════════════════════════════════════════
# 5. SOLUTION ARCHITECTURE
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(5, "Solution Architecture", "High-level component and data flow design")

pdf.body_text(
    "The solution consists of three main tiers: the Client Application tier (using MSAL), "
    "the Microsoft Entra ID cloud service (token issuance and JWKS), and the Cassandra "
    "Server tier (JWT validation and authorization)."
)

pdf.sub_header("Architecture Diagram (Text Representation)")
pdf.code_block(
    "+--------------------+       +-------------------------+       +--------------------+\n"
    "|  CLIENT SIDE       |       |  MICROSOFT ENTRA ID     |       |  CASSANDRA SERVER  |\n"
    "|--------------------|       |-------------------------|       |--------------------|\n"
    "| Application        |  (1)  | Token Endpoint          |  (3)  | EntraIdAuthenticator|\n"
    "| + Driver Plugin    |------>| /oauth2/v2.0/token      |       |                    |\n"
    "| + MSAL Library     |       |                         |       | EntraIdToken       |\n"
    "|   (msal4j /        |<------| Returns JWT             |<------| Validator          |\n"
    "|    MSAL.NET /      |  (2)  | Access Token            |  (3)  | (fetches JWKS)     |\n"
    "|    msal-python)    |       |                         |       |                    |\n"
    "|                    |       | JWKS Endpoint           |       | EntraIdAuthorizer  |\n"
    "|                    |  (4)  | /discovery/v2.0/keys    |       | (group mapping)    |\n"
    "|                    |------>|                         |       |                    |\n"
    "|                    | SASL  | (public signing keys)   |       | system_auth.       |\n"
    "|                    | PLAIN |                         |       | entra_group_roles  |\n"
    "+--------------------+       +-------------------------+       +--------------------+\n"
    "\n"
    "Flow: (1) MSAL acquires token  (2) JWT returned  (3) JWKS fetched  (4) JWT sent via SASL",
    "Architecture Overview"
)

pdf.sub_header("Design Principles")
pdf.bullet_list([
    "Zero External Dependencies: Server uses only JDK crypto (java.security.Signature) and Jackson (already in Cassandra classpath)",
    "Backward Compatible: SASL PLAIN mechanism is unchanged - JWT travels in the password field",
    "Pluggable: Implements standard IAuthenticator/IAuthorizer interfaces - can be enabled via cassandra.yaml",
    "Cacheable: JWKS keys cached for 24 hours, claims cached per-session - minimal network overhead",
    "Additive Authorization: Group permissions are UNION-ed with direct role permissions",
])

# ══════════════════════════════════════════════════════════════════
# 6. MSAL OVERVIEW
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(6, "MSAL - Microsoft Authentication Library", "The foundation for acquiring Entra ID tokens")

pdf.body_text(
    "The Microsoft Authentication Library (MSAL) is Microsoft's official library for acquiring "
    "OAuth 2.0 tokens from the Microsoft Identity Platform. MSAL handles the complexity of "
    "token caching, silent refresh, authority validation, and multiple authentication flows. "
    "It is available for Java, .NET, Python, JavaScript, and other platforms."
)

pdf.sub_header("MSAL Libraries by Platform")
pdf.table(
    ["Platform", "Library", "Package", "Min Version"],
    [
        ["Java", "msal4j", "com.microsoft.azure:msal4j", "1.13.0"],
        ["C# / .NET", "MSAL.NET", "Microsoft.Identity.Client", "4.50.0"],
        ["Python", "msal", "msal (pip)", "1.20.0"],
        ["JavaScript", "msal-browser", "@azure/msal-browser", "2.0.0"],
        ["Go", "N/A", "Use REST API directly", "N/A"],
    ],
    [30, 30, 55, 25]
)

pdf.sub_header("Key MSAL Features")
pdf.bullet_list([
    "Automatic Token Caching: Tokens stored in memory; can be serialized to disk/Redis for persistence",
    "Silent Token Refresh: Automatically refreshes expired tokens using refresh tokens, no user interaction",
    "Multiple Auth Flows: Client credentials, authorization code, device code, ROPC, managed identity",
    "Authority Validation: Verifies the Entra ID endpoint is legitimate before sending credentials",
    "Confidential Client: For server-side apps that can securely store a client secret or certificate",
    "Public Client: For desktop/mobile apps that cannot securely store a secret",
])

pdf.info_box("Key Insight: MSAL is used ONLY on the client side. The Cassandra server validates "
             "JWT tokens using JDK crypto, NOT MSAL.")

# ══════════════════════════════════════════════════════════════════
# 7. MSAL CLIENT SIDE
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(7, "MSAL on Client Side - Token Acquisition", "How client applications obtain JWT access tokens")

pdf.body_text(
    "Each client driver plugin uses MSAL to acquire a JWT access token before connecting "
    "to Cassandra. The token is scoped to api://{client_id}/.default, which represents "
    "all permissions defined in the app registration. MSAL automatically caches the token "
    "and refreshes it when it expires."
)

pdf.sub_header("Authentication Flows")

flows = [
    ("Client Credentials (Recommended for Services)",
     "The application authenticates using its own identity (client_id + client_secret or certificate). "
     "No user context is involved. Best for: backend services, batch jobs, microservices.",
     "app = ConfidentialClientApplication.builder(clientId,\n"
     "    ClientCredentialFactory.createFromSecret(secret))\n"
     "    .authority(authority).build();\n"
     "token = app.acquireToken(ClientCredentialParameters\n"
     "    .builder(scopes).build()).get().accessToken();"),
    ("Managed Identity (Recommended for Azure)",
     "Azure automatically provides tokens to VMs, AKS pods, and other Azure resources. "
     "No secrets to manage. Uses the Azure Instance Metadata Service (IMDS) at 169.254.169.254.",
     "app = ManagedIdentityApplication.builder(\n"
     "    ManagedIdentityId.systemAssigned()).build();\n"
     "token = app.acquireTokenForManagedIdentity(\n"
     "    ManagedIdentityParameters.builder(resource)\n"
     "    .build()).get().accessToken();"),
    ("Interactive / Device Code (For Developers)",
     "User signs in via a browser or enters a device code. Supports MFA and Conditional Access. "
     "Best for: developer tools, CQLSH, one-off admin tasks.",
     "app = PublicClientApplication.builder(clientId)\n"
     "    .authority(authority).build();\n"
     "token = app.acquireToken(DeviceCodeFlowParameters\n"
     "    .builder(scopes, cb).build()).get().accessToken();"),
    ("ROPC - Username/Password (Legacy Only)",
     "Direct username/password grant. Does NOT support MFA. Not recommended for production. "
     "Use only for migration from PasswordAuthenticator.",
     "token = app.acquireToken(UserNamePasswordParameters\n"
     "    .builder(scopes, username, password.toCharArray())\n"
     "    .build()).get().accessToken();"),
]

for title, desc, code in flows:
    pdf.sub_header(title)
    pdf.body_text(desc)
    pdf.code_block(code, f"Example: {title.split('(')[0].strip()}")

# ══════════════════════════════════════════════════════════════════
# 8. MSAL SERVER SIDE
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(8, "MSAL on Server Side - JWT Validation", "How Cassandra validates tokens WITHOUT MSAL at runtime")

pdf.info_box("IMPORTANT: The Cassandra server does NOT use MSAL at runtime. MSAL is client-only. "
             "The server validates tokens using JDK crypto - zero external dependencies.")

pdf.body_text(
    "When a client sends a JWT token, the EntraIdTokenValidator processes it through a "
    "six-step validation pipeline using only JDK built-in classes. No external libraries "
    "are required beyond Jackson (which is already in Cassandra's classpath)."
)

pdf.sub_header("JWT Validation Pipeline")
pdf.numbered_list([
    "Parse JWT: Split the token string at '.' separators into header, payload, and signature sections. Decode each from base64url encoding using java.util.Base64.getUrlDecoder().",
    "Read Header: Parse the JSON header to extract 'kid' (key identifier) and 'alg' (algorithm). Verify that 'alg' is 'RS256' - reject all other algorithms.",
    "Fetch JWKS Public Keys: HTTP GET to https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys. Parse the JWKS response to extract RSA public keys. Cache keys in ConcurrentHashMap for 24 hours.",
    "Verify RS256 Signature: Use java.security.Signature.getInstance('SHA256withRSA') to verify the token signature against the public key matching the 'kid' from the header.",
    "Validate Claims: Check issuer (iss) matches tenant, audience (aud) matches client_id, expiry (exp) is in the future (with 5-minute clock skew tolerance), not-before (nbf) is in the past.",
    "Extract Identity: Read preferred_username (or upn, email, sub, oid as fallbacks) for the principal name. Extract 'groups' array (Entra ID group UUIDs) and 'roles' array (app roles).",
])

pdf.sub_header("JDK Classes Used")
pdf.table(
    ["JDK Class", "Purpose", "Package"],
    [
        ["Signature", "RS256 signature verification", "java.security"],
        ["KeyFactory", "RSA public key construction", "java.security"],
        ["RSAPublicKeySpec", "Key spec from modulus + exponent", "java.security.spec"],
        ["Base64.getUrlDecoder()", "Base64url decoding (JWT standard)", "java.util"],
        ["HttpURLConnection", "JWKS endpoint HTTP request", "java.net"],
        ["ConcurrentHashMap", "Thread-safe key & claims caching", "java.util.concurrent"],
    ],
    [45, 60, 40]
)

# ══════════════════════════════════════════════════════════════════
# 9. AUTHENTICATION DATA FLOW
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(9, "Authentication Data Flow", "Complete step-by-step token lifecycle")

pdf.body_text(
    "The following sequence describes the complete authentication flow from the client "
    "application requesting a token to Cassandra granting access."
)

pdf.sub_header("Detailed Sequence")
steps = [
    ("Step 1: Client calls MSAL", "Client Application -> MSAL Library",
     "The application calls MSAL's acquireToken() method with the appropriate scope "
     "(api://{client_id}/.default). MSAL first checks its in-memory cache for a valid, "
     "non-expired token."),
    ("Step 2: MSAL contacts Entra ID", "MSAL Library -> Entra ID Token Endpoint",
     "If no cached token is available, MSAL sends an OAuth 2.0 token request to "
     "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token with the client credentials "
     "(or other grant type parameters)."),
    ("Step 3: Entra ID issues JWT", "Entra ID -> MSAL Library",
     "Entra ID validates the credentials, checks Conditional Access policies, and returns a "
     "signed JWT access token. The token contains claims including the user's identity, "
     "group memberships, and assigned app roles."),
    ("Step 4: MSAL returns token", "MSAL Library -> Client Application",
     "MSAL caches the token (with its expiry time) and returns it to the application. "
     "Subsequent calls to acquireToken() will return the cached token until it expires."),
    ("Step 5: Driver sends SASL PLAIN", "Driver -> Cassandra (Native Protocol)",
     "The Cassandra driver sends an AUTH_RESPONSE frame containing a SASL PLAIN message: "
     "NUL + preferred_username + NUL + JWT_access_token. The JWT is placed in the password field."),
    ("Step 6: Authenticator fetches JWKS", "Cassandra -> Entra ID JWKS Endpoint",
     "EntraIdTokenValidator fetches the JWKS public keys from "
     "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys (only if the cache is empty or expired)."),
    ("Step 7: Token validated", "Cassandra (internal)",
     "The validator verifies the RS256 signature, checks all claims (iss, aud, exp, nbf), "
     "extracts the principal name and group memberships, caches the claims, and returns "
     "an AuthenticatedUser to the connection."),
]

for title, flow, desc in steps:
    pdf.sub_header(f"{title}")
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(*AZURE_BLUE)
    pdf.cell(0, 5, flow, 0, 1, 'L')
    pdf.set_text_color(*BLACK)
    pdf.body_text(desc)

# ══════════════════════════════════════════════════════════════════
# 10. AUTHORIZATION & GROUP MAPPING
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(10, "Authorization & Group-to-Role Mapping",
                   "How Entra ID groups and app roles map to Cassandra permissions")

pdf.body_text(
    "EntraIdAuthorizer extends Cassandra's CassandraAuthorizer to add a group-based "
    "authorization layer. When checking permissions, it first runs the standard Cassandra "
    "permission check (role_permissions), then additionally checks if any of the user's "
    "Entra ID groups are mapped to Cassandra roles that grant the requested permission."
)

pdf.sub_header("Authorization Decision Flow")
pdf.numbered_list([
    "User authenticates with JWT; claims (groups, roles) are cached by the authenticator",
    "Application issues a CQL statement (e.g., SELECT * FROM keyspace.table)",
    "EntraIdAuthorizer.authorize() is called with (user, resource, permission)",
    "Step 1: Call super.authorize() - standard CassandraAuthorizer checks role_permissions for the user's direct Cassandra role",
    "Step 2: If denied, look up user's Entra ID group claim UUIDs from the claims cache",
    "Step 3: For each group UUID, query system_auth.entra_group_roles to find mapped Cassandra roles",
    "Step 4: For each mapped role, check role_permissions for the requested permission",
    "Step 5: UNION all permissions - if any path grants access, the request is allowed",
])

pdf.sub_header("Group-to-Role Mapping Table Schema")
pdf.code_block(
    "CREATE TABLE IF NOT EXISTS system_auth.entra_group_roles (\n"
    "    group_id        text,       -- Entra ID group UUID or app role name\n"
    "    cassandra_role  text,       -- Target Cassandra role name\n"
    "    PRIMARY KEY (group_id, cassandra_role)\n"
    ");\n"
    "\n"
    "-- Example mappings:\n"
    "INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)\n"
    "VALUES ('a1b2c3d4-...', 'db_readers');        -- Security group -> role\n"
    "\n"
    "INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)\n"
    "VALUES ('CassandraAdmin', 'cassandra_admin');  -- App role -> role\n"
    "\n"
    "INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)\n"
    "VALUES ('e5f6g7h8-...', 'db_writers');         -- Another group -> role",
    "Schema & Example Mappings"
)

# ══════════════════════════════════════════════════════════════════
# 11. AZURE PORTAL SETUP
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(11, "Azure Portal Setup - Complete Guide",
                   "Step-by-step walkthrough for service providers")

portal_steps = [
    ("Step 1: Register the Application",
     "Navigate to Azure Portal > Microsoft Entra ID > App registrations > New registration.\n\n"
     "Name: 'Apache Cassandra Cluster' (or your cluster name)\n"
     "Supported account types: 'Accounts in this organizational directory only' (Single tenant)\n"
     "Redirect URI: Leave blank (not needed for client credentials)\n\n"
     "After registration, note down:\n"
     "- Application (client) ID -> This is your client_id\n"
     "- Directory (tenant) ID -> This is your tenant_id"),

    ("Step 2: Expose an API",
     "Navigate to your app registration > Expose an API > Set Application ID URI.\n\n"
     "Accept the default: api://{client-id}\n"
     "This creates the .default scope used by client applications.\n"
     "Scope: api://{client-id}/.default"),

    ("Step 3: Create App Roles",
     "Navigate to App roles > Create app role.\n\n"
     "Create the following roles:\n"
     "- Display name: 'Cassandra Admin', Value: 'CassandraAdmin', Allowed member types: Users/Groups\n"
     "- Display name: 'Cassandra Reader', Value: 'CassandraReader', Allowed member types: Users/Groups\n"
     "- Display name: 'Cassandra Writer', Value: 'CassandraWriter', Allowed member types: Users/Groups\n\n"
     "These roles will appear in the 'roles' claim of the JWT token."),

    ("Step 4: Configure Group Claims",
     "Navigate to Token configuration > Add groups claim.\n\n"
     "Select: 'Security groups'\n"
     "Under 'Customize token properties by type':\n"
     "  Access token > Emit groups as: 'Group ID'\n\n"
     "This adds a 'groups' claim to the JWT containing the UUIDs of the user's security groups."),

    ("Step 5: Create Client Secret",
     "Navigate to Certificates & secrets > Client secrets > New client secret.\n\n"
     "Description: 'Cassandra auth'\n"
     "Expires: Choose appropriate duration (6 months, 12 months, 24 months, or custom)\n\n"
     "IMPORTANT: Copy the 'Value' immediately - it will not be shown again.\n"
     "This is your client_secret for the client credentials flow."),

    ("Step 6: API Permissions",
     "Navigate to API permissions.\n\n"
     "The default 'User.Read' permission from Microsoft Graph is typically sufficient.\n"
     "If using client credentials flow (service-to-service), you may not need additional "
     "permissions. The .default scope inherits from the Application ID URI."),

    ("Step 7: Create Security Groups",
     "Navigate to Microsoft Entra ID > Groups > New group.\n\n"
     "Group type: Security\n"
     "Name: 'Cassandra Admins' / 'Cassandra Readers' / 'Cassandra Writers'\n"
     "Add members as needed.\n\n"
     "Note the Object ID of each group - these are the UUIDs you'll use in the "
     "entra_group_roles mapping table."),

    ("Step 8: Assign Users and Groups",
     "Navigate to Enterprise applications > Your application > Users and groups > Add user/group.\n\n"
     "Assign users and/or groups to the application. Optionally assign app roles here.\n"
     "Only assigned users/groups will be able to obtain tokens for the application."),

    ("Step 9: Configure Conditional Access (Optional)",
     "Navigate to Security > Conditional Access > New policy.\n\n"
     "Target: Your Cassandra application\n"
     "Conditions: Any (or specific locations, device platforms, risk levels)\n"
     "Grant: Require MFA, and/or require compliant device\n\n"
     "This enforces MFA at token issuance time - Cassandra doesn't need to know about MFA."),

    ("Step 10: Managed Identity (Azure Workloads)",
     "For Azure VMs: Settings > Identity > System assigned > Status: On\n"
     "For AKS: Configure workload identity federation\n\n"
     "Then assign the Application role to the managed identity:\n"
     "az role assignment create --assignee <MI-object-id> --role 'CassandraReader' ...\n\n"
     "The application running on this VM/pod can now acquire tokens without any secrets."),
]

for title, desc in portal_steps:
    pdf.sub_header(title)
    pdf.body_text(desc)
    if pdf.get_y() > 260:
        pdf.add_page()

# ══════════════════════════════════════════════════════════════════
# 12. SERVER-SIDE COMPONENTS
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(12, "Server-Side Components", "Three Java classes implementing Cassandra's auth interfaces")

pdf.info_box("Total: ~1,074 lines of Java code  |  External dependencies: 0  |  Target: Java 8  |  Tests: 18 passing")

classes = [
    ("EntraIdAuthenticator",
     "Implements Cassandra's IAuthenticator interface to handle JWT-based authentication.",
     [
         "Returns EntraIdSaslNegotiator for SASL PLAIN challenges",
         "Decodes NUL-separated SASL response (username + JWT)",
         "Delegates to EntraIdTokenValidator for JWT validation",
         "Caches validated claims (groups, roles) in ConcurrentHashMap<String, Map>",
         "Returns AuthenticatedUser with the principal name from the JWT",
         "Principal name resolution: preferred_username > upn > email > sub > oid",
         "Thread-safe: ConcurrentHashMap for claims, volatile for validator reference",
     ]),
    ("EntraIdTokenValidator",
     "Pure JWT token validation engine using only JDK cryptography classes.",
     [
         "Fetches JWKS from login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
         "Caches RSA PublicKey objects in ConcurrentHashMap (24-hour TTL)",
         "Verifies RS256 (SHA256withRSA) signature using java.security.Signature",
         "Validates all standard claims: iss, aud, exp, nbf with 5-min clock skew",
         "Supports both v1 and v2 Entra ID issuers automatically",
         "Returns Map<String, Object> with all validated claims",
         "Double-checked locking for thread-safe JWKS refresh",
     ]),
    ("EntraIdAuthorizer",
     "Extends CassandraAuthorizer to add Entra ID group-based authorization.",
     [
         "Inherits all standard CassandraAuthorizer behavior (role_permissions)",
         "Adds group-based authorization layer on top of standard checks",
         "Creates system_auth.entra_group_roles table during setup()",
         "Reads claims (groups, roles) from authenticator's ConcurrentHashMap cache",
         "For each Entra ID group UUID, looks up mapped Cassandra roles",
         "UNIONs direct permissions + group-mapped permissions",
         "Falls back to standard behavior if no Entra ID claims are available",
     ]),
]

for name, desc, features in classes:
    pdf.sub_header(name)
    pdf.body_text(desc)
    pdf.bullet_list(features)

# ══════════════════════════════════════════════════════════════════
# 13. SERVER DEPLOYMENT OPTIONS
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(13, "Server Deployment Options", "Plugin JAR vs Source Integration")

pdf.sub_header("Option A: Plugin JAR (Recommended)")
pdf.body_text(
    "The recommended deployment method. Build a standalone JAR that is dropped into "
    "Cassandra's lib/ directory. No modification to Cassandra source code is needed. "
    "Works with any stock Apache Cassandra 4.1.x installation."
)

pdf.code_block(
    "# Build the plugin JAR\n"
    "cd server-plugin\n"
    "mvn clean package\n"
    "\n"
    "# Deploy\n"
    "cp target/cassandra-entra-id-auth-1.0.0.jar $CASSANDRA_HOME/lib/\n"
    "\n"
    "# Configure (create conf/entra-id.properties)\n"
    "tenant_id=YOUR-TENANT-ID\n"
    "client_id=YOUR-CLIENT-ID\n"
    "\n"
    "# Or use JVM system properties instead\n"
    "# Add to jvm-server.options:\n"
    "# -Dcassandra.entra.tenant_id=YOUR-TENANT-ID\n"
    "# -Dcassandra.entra.client_id=YOUR-CLIENT-ID",
    "Plugin JAR Build & Deploy"
)

pdf.sub_header("Option B: Source Integration")
pdf.body_text(
    "For organizations that build Cassandra from source, the EntraID classes can be compiled "
    "directly into cassandra-all.jar. This approach modifies Config.java to add entra_tenant_id "
    "and entra_client_id fields, allowing configuration via cassandra.yaml."
)

pdf.code_block(
    "# Modified files:\n"
    "#   src/java/org/apache/cassandra/config/Config.java  (+ 2 fields)\n"
    "#   conf/cassandra.yaml                               (+ documentation)\n"
    "#   src/java/org/apache/cassandra/auth/EntraId*.java  (3 new classes)\n"
    "#   test/unit/.../EntraIdAuthenticatorTest.java        (1 new test)\n"
    "\n"
    "# Build entire Cassandra\n"
    "ant jar\n"
    "\n"
    "# Configure in cassandra.yaml\n"
    "entra_tenant_id: YOUR-TENANT-ID\n"
    "entra_client_id: YOUR-CLIENT-ID",
    "Source Integration Build & Configure"
)

pdf.sub_header("Comparison")
pdf.table(
    ["Aspect", "Plugin JAR", "Source Integration"],
    [
        ["Cassandra modification", "None", "Config.java + YAML"],
        ["Build process", "mvn clean package", "ant jar (full Cassandra)"],
        ["Upgrade path", "Replace JAR", "Merge with source updates"],
        ["Configuration", "Properties file / JVM props", "cassandra.yaml"],
        ["Stock Cassandra", "Yes", "No (custom build)"],
        ["Testing", "Maven Surefire", "Ant JUnit"],
    ],
    [45, 60, 60]
)

# ══════════════════════════════════════════════════════════════════
# 14. CASSANDRA CONFIGURATION
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(14, "Cassandra Configuration", "cassandra.yaml and supporting files")

pdf.sub_header("cassandra.yaml (Required Changes)")
pdf.code_block(
    "# Authentication - use Entra ID JWT tokens\n"
    "authenticator: EntraIdAuthenticator\n"
    "\n"
    "# Authorization - standard + Entra ID group mapping\n"
    "authorizer: EntraIdAuthorizer\n"
    "\n"
    "# Role manager - unchanged\n"
    "role_manager: CassandraRoleManager\n"
    "\n"
    "# Source integration only (not needed for plugin JAR):\n"
    "# entra_tenant_id: 72f988bf-86f1-41af-91ab-2d7cd011db47\n"
    "# entra_client_id: 6731de76-14a6-49ae-97bc-6eba6914391e",
    "cassandra.yaml"
)

pdf.sub_header("Configuration Precedence (Plugin JAR)")
pdf.numbered_list([
    "JVM system properties: -Dcassandra.entra.tenant_id=... (highest priority)",
    "Properties file: $CASSANDRA_HOME/conf/entra-id.properties (default location)",
    "Custom properties file: -Dcassandra.entra.config=/path/to/custom.properties",
])

pdf.sub_header("Setting Up Group-to-Role Mappings")
pdf.code_block(
    "-- Connect as superuser and create the target Cassandra roles\n"
    "CREATE ROLE db_readers WITH LOGIN = false;\n"
    "CREATE ROLE db_writers WITH LOGIN = false;\n"
    "CREATE ROLE db_admins WITH LOGIN = false;\n"
    "\n"
    "-- Grant permissions to roles\n"
    "GRANT SELECT ON KEYSPACE production TO db_readers;\n"
    "GRANT SELECT, MODIFY ON KEYSPACE production TO db_writers;\n"
    "GRANT ALL ON KEYSPACE production TO db_admins;\n"
    "\n"
    "-- Map Entra ID groups to Cassandra roles\n"
    "INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)\n"
    "VALUES ('aad-readers-group-uuid', 'db_readers');\n"
    "\n"
    "INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)\n"
    "VALUES ('aad-writers-group-uuid', 'db_writers');\n"
    "\n"
    "INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)\n"
    "VALUES ('CassandraAdmin', 'db_admins');  -- App role mapping",
    "Group-to-Role Mapping Setup"
)

# ══════════════════════════════════════════════════════════════════
# 15. JAVA DRIVERS
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(15, "Client Driver - Java (DataStax 3.x & 4.x)",
                   "Pre-built Maven artifacts with MSAL4J shaded inside")

pdf.sub_header("DataStax Java Driver 3.x")
pdf.body_text(
    "The Driver 3.x plugin implements AuthProvider from com.datastax.driver.core. "
    "It uses MSAL4J to acquire tokens and constructs SASL PLAIN responses. "
    "The artifact is an uber JAR built with Maven Shade to avoid classpath conflicts."
)

pdf.code_block(
    "<!-- Maven dependency -->\n"
    "<dependency>\n"
    "  <groupId>org.apache.cassandra</groupId>\n"
    "  <artifactId>cassandra-entra-id-auth-driver3</artifactId>\n"
    "  <version>1.0.0</version>\n"
    "</dependency>\n"
    "\n"
    "// Java usage\n"
    "EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()\n"
    "    .tenantId(\"YOUR-TENANT-ID\")\n"
    "    .clientId(\"YOUR-CLIENT-ID\")\n"
    "    .clientSecret(\"YOUR-SECRET\")\n"
    "    .build();\n"
    "\n"
    "Cluster cluster = Cluster.builder()\n"
    "    .addContactPoint(\"cassandra-host\")\n"
    "    .withAuthProvider(authProvider)\n"
    "    .build();\n"
    "Session session = cluster.connect();",
    "DataStax Driver 3.x - Maven + Code"
)

pdf.sub_header("DataStax Java Driver 4.x")
pdf.body_text(
    "The Driver 4.x plugin implements the new AuthProvider interface from "
    "com.datastax.oss.driver.api.core.auth. The API uses Node-level authentication "
    "and the Authenticator inner class pattern."
)

pdf.code_block(
    "<!-- Maven dependency -->\n"
    "<dependency>\n"
    "  <groupId>org.apache.cassandra</groupId>\n"
    "  <artifactId>cassandra-entra-id-auth-driver4</artifactId>\n"
    "  <version>1.0.0</version>\n"
    "</dependency>\n"
    "\n"
    "// Java usage (Driver 4.x)\n"
    "EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()\n"
    "    .tenantId(\"YOUR-TENANT-ID\")\n"
    "    .clientId(\"YOUR-CLIENT-ID\")\n"
    "    .clientSecret(\"YOUR-SECRET\")\n"
    "    .build();\n"
    "\n"
    "CqlSession session = CqlSession.builder()\n"
    "    .addContactPoint(new InetSocketAddress(\"cassandra-host\", 9042))\n"
    "    .withAuthProvider(authProvider)\n"
    "    .withLocalDatacenter(\"datacenter1\")\n"
    "    .build();",
    "DataStax Driver 4.x - Maven + Code"
)

pdf.sub_header("Managed Identity Example (Both Drivers)")
pdf.code_block(
    "// No secrets needed - Azure provides tokens automatically\n"
    "EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()\n"
    "    .tenantId(\"YOUR-TENANT-ID\")\n"
    "    .clientId(\"YOUR-CLIENT-ID\")\n"
    "    .useManagedIdentity(true)\n"
    "    .build();",
    "Managed Identity (Azure VM / AKS)"
)

# ══════════════════════════════════════════════════════════════════
# 16. C# DRIVER
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(16, "Client Driver - C# (.NET)", "NuGet package with MSAL.NET integration")

pdf.body_text(
    "The C# driver plugin implements IAuthProvider and IAuthProviderNamed from the "
    "CassandraCSharpDriver NuGet package. It uses MSAL.NET (Microsoft.Identity.Client) "
    "for token acquisition and supports all authentication flows."
)

pdf.code_block(
    "// Install via NuGet\n"
    "dotnet add package Apache.Cassandra.EntraIdAuth\n"
    "\n"
    "// C# - Client Credentials\n"
    "using Apache.Cassandra.EntraIdAuth;\n"
    "using Cassandra;\n"
    "\n"
    "var authProvider = new EntraIdAuthProvider(\n"
    "    tenantId: \"YOUR-TENANT-ID\",\n"
    "    clientId: \"YOUR-CLIENT-ID\",\n"
    "    clientSecret: \"YOUR-SECRET\");\n"
    "\n"
    "var cluster = Cluster.Builder()\n"
    "    .AddContactPoint(\"cassandra-host\")\n"
    "    .WithAuthProvider(authProvider)\n"
    "    .Build();\n"
    "var session = cluster.Connect();\n"
    "\n"
    "// Managed Identity\n"
    "var authProvider = new EntraIdAuthProvider(\n"
    "    tenantId: \"YOUR-TENANT-ID\",\n"
    "    clientId: \"YOUR-CLIENT-ID\",\n"
    "    useManagedIdentity: true);",
    "C# .NET Example"
)

pdf.sub_header("NuGet Package Details")
pdf.table(
    ["Property", "Value"],
    [
        ["Package Name", "Apache.Cassandra.EntraIdAuth"],
        ["Target Framework", "netstandard2.0 (compatible with .NET 5/6/7/8)"],
        ["Dependencies", "CassandraCSharpDriver >= 3.19.0, Microsoft.Identity.Client >= 4.50.0"],
        ["Source", "driver-plugins/csharp/"],
    ],
    [50, 110]
)

# ══════════════════════════════════════════════════════════════════
# 17. PYTHON DRIVER
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(17, "Client Driver - Python", "pip package with msal integration")

pdf.code_block(
    "# Install\n"
    "pip install cassandra-entra-id-auth\n"
    "\n"
    "# Python - Client Credentials\n"
    "from cassandra_entra_id_auth import EntraIdAuthProvider\n"
    "from cassandra.cluster import Cluster\n"
    "\n"
    "auth_provider = EntraIdAuthProvider(\n"
    "    tenant_id='YOUR-TENANT-ID',\n"
    "    client_id='YOUR-CLIENT-ID',\n"
    "    client_secret='YOUR-SECRET'\n"
    ")\n"
    "\n"
    "cluster = Cluster(\n"
    "    contact_points=['cassandra-host'],\n"
    "    auth_provider=auth_provider\n"
    ")\n"
    "session = cluster.connect()\n"
    "\n"
    "# Managed Identity\n"
    "auth_provider = EntraIdAuthProvider(\n"
    "    tenant_id='YOUR-TENANT-ID',\n"
    "    client_id='YOUR-CLIENT-ID',\n"
    "    use_managed_identity=True\n"
    ")",
    "Python pip Package"
)

pdf.sub_header("Supported Authentication Flows")
pdf.table(
    ["Flow", "Parameter", "Requires"],
    [
        ["Client Credentials", "client_secret='...'", "App registration + secret"],
        ["Managed Identity", "use_managed_identity=True", "Azure VM/AKS"],
        ["Username/Password", "username='...', password='...'", "User credentials (no MFA)"],
        ["Device Code", "use_device_code=True", "Browser on another device"],
        ["Interactive", "use_interactive=True", "Local browser"],
    ],
    [40, 55, 65]
)

# ══════════════════════════════════════════════════════════════════
# 18. CQLSH
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(18, "CQLSH Integration", "Native Entra ID support built into Cassandra's cqlsh")

pdf.body_text(
    "CQLSH now includes a built-in Entra ID auth provider module at "
    "pylib/cqlshlib/entra_id_auth_provider.py. This module ships with Cassandra "
    "and does not require separate installation. The only external dependency is "
    "the msal Python library (pip install msal)."
)

pdf.sub_header("Configuration via cqlshrc")
pdf.code_block(
    "# ~/.cassandra/cqlshrc\n"
    "[auth_provider]\n"
    "module = cqlshlib.entra_id_auth_provider\n"
    "classname = EntraIdAuthProvider\n"
    "tenant_id = YOUR-TENANT-ID\n"
    "client_id = YOUR-CLIENT-ID\n"
    "client_secret = YOUR-SECRET\n"
    "\n"
    "# Or using environment variables:\n"
    "# export ENTRA_TENANT_ID=YOUR-TENANT-ID\n"
    "# export ENTRA_CLIENT_ID=YOUR-CLIENT-ID\n"
    "# export ENTRA_CLIENT_SECRET=YOUR-SECRET",
    "cqlshrc Configuration"
)

pdf.sub_header("CQLSH Code Changes")
pdf.bullet_list([
    "bin/cqlsh.py: Enhanced do_login to support token re-authentication without password prompt",
    "bin/cqlsh.py: Added username extraction from JWT preferred_username claim for shell prompt",
    "pylib/cqlshlib/entra_id_auth_provider.py: New module implementing PlainTextAuthProvider-compatible interface",
    "LOGIN command now acquires a fresh Entra ID token automatically",
    "Shell prompt shows the actual Entra ID identity: user@contoso.com@cqlsh>",
])

# ══════════════════════════════════════════════════════════════════
# 19. SASL WIRE FORMAT
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(19, "SASL PLAIN Wire Format", "How JWT tokens travel over the Cassandra native protocol")

pdf.body_text(
    "The solution uses the existing SASL PLAIN mechanism defined in RFC 4616. "
    "No changes to Cassandra's native protocol are required. The JWT access token "
    "is placed in the 'password' field of the SASL response."
)

pdf.sub_header("Wire Format")
pdf.code_block(
    "SASL PLAIN Response (RFC 4616):\n"
    "\n"
    "+----------+------+------------------+------+--------------------+\n"
    "| authzId  | NUL  | authnId          | NUL  | password           |\n"
    "| (empty)  | 0x00 | user@contoso.com | 0x00 | eyJhbGciOiJSUzI1. |\n"
    "|          |      | (from JWT)       |      | ..(JWT token)..    |\n"
    "+----------+------+------------------+------+--------------------+\n"
    "\n"
    "authzId:  Empty (not used)\n"
    "authnId:  The preferred_username from the JWT (advisory only)\n"
    "password: The FULL JWT access token (typically 1000-2000 bytes)\n"
    "\n"
    "Note: The JWT in the password field is the PRIMARY credential.\n"
    "The authnId (username) is extracted from the JWT claims after validation.",
    "SASL PLAIN Response Format"
)

pdf.sub_header("Protocol Compatibility")
pdf.bullet_list([
    "Native protocol v3, v4, v5 all support SASL PLAIN - no protocol changes needed",
    "Maximum SASL response size is not constrained by the protocol (JWT fits easily)",
    "Existing client drivers already implement SASL PLAIN - only the credentials change",
    "TLS encryption is CRITICAL - JWT tokens are bearer tokens that must be protected in transit",
])

# ══════════════════════════════════════════════════════════════════
# 20. JWKS DEEP DIVE
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(20, "JWKS & Token Validation Deep Dive",
                   "How the server verifies tokens without calling Entra ID per request")

pdf.sub_header("JWKS Key Cache")
pdf.body_text(
    "The EntraIdTokenValidator maintains a cache of RSA public keys fetched from the Entra ID JWKS endpoint. "
    "Keys are cached for 24 hours and refreshed automatically. The cache uses a ConcurrentHashMap "
    "for thread safety and double-checked locking for the refresh mechanism."
)

pdf.code_block(
    "JWKS Endpoint:\n"
    "  https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys\n"
    "\n"
    "Response format:\n"
    "{\n"
    '  "keys": [\n'
    "    {\n"
    '      "kty": "RSA",\n'
    '      "use": "sig",\n'
    '      "kid": "nOo3ZDrODXEK1jKWhXslHR_KXEg",\n'
    '      "n":   "0vx7agoebGcQSuu...",     // modulus (base64url)\n'
    '      "e":   "AQAB"                     // exponent (base64url)\n'
    "    },\n"
    "    { ... more keys ... }\n"
    "  ]\n"
    "}",
    "JWKS Response Structure"
)

pdf.sub_header("JWT Claim Validation Rules")
pdf.table(
    ["Claim", "Validation Rule", "Failure Action"],
    [
        ["alg", "Must be 'RS256'", "Reject token immediately"],
        ["kid", "Must match a JWKS key", "Refresh JWKS, retry once"],
        ["iss", "Must be v1 or v2 Entra ID issuer", "Reject with 'invalid issuer'"],
        ["aud", "Must equal configured client_id", "Reject with 'invalid audience'"],
        ["exp", "exp + 300s > now", "Reject with 'token expired'"],
        ["nbf", "nbf - 300s < now", "Reject with 'token not yet valid'"],
        ["signature", "RS256 verify against JWKS key", "Reject with 'invalid signature'"],
    ],
    [25, 75, 55]
)

# ══════════════════════════════════════════════════════════════════
# 21. MANAGED IDENTITY
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(21, "Azure Managed Identity Deep Dive",
                   "Zero-secret authentication for Azure-hosted workloads")

pdf.body_text(
    "Azure Managed Identity is the recommended authentication method for workloads running "
    "on Azure infrastructure. It eliminates the need to manage client secrets or certificates. "
    "Azure automatically provides a managed credential that MSAL uses to acquire tokens."
)

pdf.sub_header("How Managed Identity Works")
pdf.numbered_list([
    "Azure assigns a service principal to the VM/AKS/App Service resource",
    "A token endpoint is available at the Azure Instance Metadata Service (IMDS): http://169.254.169.254/metadata/identity/oauth2/token",
    "MSAL detects that it's running on Azure and automatically calls IMDS",
    "IMDS returns a JWT access token scoped to the requested resource",
    "The app sends this JWT to Cassandra via the driver's auth provider",
    "No secrets, certificates, or credentials are stored anywhere in the application",
])

pdf.sub_header("Types of Managed Identity")
pdf.table(
    ["Type", "System-Assigned", "User-Assigned"],
    [
        ["Lifecycle", "Tied to Azure resource", "Independent resource"],
        ["Sharing", "1:1 with resource", "Can be shared across resources"],
        ["Identity", "Auto-created, auto-deleted", "Manually created, manually deleted"],
        ["Use Case", "Single service", "Shared across microservices"],
        ["AKS Support", "Node-level", "Pod-level (workload identity)"],
    ],
    [30, 65, 65]
)

pdf.sub_header("Setup Commands")
pdf.code_block(
    "# Enable system-assigned managed identity on a VM\n"
    "az vm identity assign -g myResourceGroup -n myVM\n"
    "\n"
    "# Get the managed identity's object ID\n"
    "az vm show -g myResourceGroup -n myVM --query identity.principalId -o tsv\n"
    "\n"
    "# Assign an app role to the managed identity\n"
    "az ad sp app-role-assignment add \\\n"
    "  --assignee-object-id <MI-principal-id> \\\n"
    "  --resource-id <cassandra-app-sp-id> \\\n"
    "  --app-role-id <CassandraReader-role-id>",
    "Azure CLI - Managed Identity Setup"
)

# ══════════════════════════════════════════════════════════════════
# 22. SECURITY
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(22, "Security Considerations", "Defence in depth for production deployments")

categories = [
    ("Transport Layer Security", [
        "Enable client-to-node TLS encryption (native_transport_port_ssl: 9142)",
        "JWT tokens are bearer tokens - they MUST be encrypted in transit",
        "Use TLS 1.2+ with strong cipher suites (AES-256-GCM preferred)",
        "Mutual TLS (mTLS) can be layered on top for additional security",
        "Internode encryption should also be enabled for gossip traffic",
    ]),
    ("Token Security", [
        "JWT access tokens are typically valid for 1 hour (configurable in Entra ID)",
        "Clock skew tolerance: 5 minutes (300 seconds) to handle clock drift",
        "JWKS keys are refreshed every 24 hours (cached between refreshes)",
        "Only RS256 (RSA + SHA-256) signature algorithm is accepted",
        "Token replay is mitigated by short lifetime + TLS + unique `jti` claim",
    ]),
    ("Configuration Security", [
        "Store client secrets in Azure Key Vault (not in plain text config files)",
        "Use Managed Identity wherever possible (eliminates secrets entirely)",
        "Set file permissions on conf/entra-id.properties (chmod 600)",
        "Validate tenant_id and client_id format at startup (prevent injection)",
        "Log authentication failures but never log the full JWT token",
    ]),
    ("Audit and Monitoring", [
        "All authentication events are logged via Cassandra's SLF4J logging",
        "Failed validation includes specific reason codes (expired, bad signature, etc.)",
        "Entra ID sign-in logs capture all token requests in Azure Monitor",
        "Conditional Access policies are enforced at token issuance time",
        "Set up Azure alerts for unusual sign-in activity or failed authentications",
    ]),
]

for title, items in categories:
    pdf.sub_header(title)
    pdf.bullet_list(items)

# ══════════════════════════════════════════════════════════════════
# 23. BACKWARD COMPATIBILITY
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(23, "Backward Compatibility & Migration",
                   "Moving from PasswordAuthenticator to EntraID")

pdf.sub_header("What Changes")
pdf.table(
    ["Aspect", "Before (Password)", "After (Entra ID)"],
    [
        ["Authenticator", "PasswordAuthenticator", "EntraIdAuthenticator"],
        ["Authorizer", "CassandraAuthorizer", "EntraIdAuthorizer"],
        ["Credentials", "Username + bcrypt password", "JWT access token"],
        ["Identity source", "system_auth.roles", "Microsoft Entra ID"],
        ["MFA", "Not supported", "Via Conditional Access"],
        ["Group-based auth", "Not supported", "entra_group_roles table"],
        ["Audit", "Cassandra logs only", "Entra ID + Cassandra"],
    ],
    [35, 55, 65]
)

pdf.sub_header("Rolling Migration Plan")
pdf.numbered_list([
    "Deploy plugin JAR to all nodes (copy to lib/) - no restart needed yet",
    "Create Cassandra roles matching Entra ID principal names (preferred_username fields)",
    "Create and populate entra_group_roles mapping table entries",
    "Update cassandra.yaml on each node: authenticator -> EntraIdAuthenticator, authorizer -> EntraIdAuthorizer",
    "Rolling restart the cluster: one node at a time, verify auth on each before proceeding",
    "Update client applications to use MSAL-based auth providers (driver plugins)",
    "Run both auth methods in parallel during transition (create roles with both password and Entra ID access)",
    "(Optional) Disable legacy passwords once all clients are migrated",
])

pdf.info_box("Tip: Create Cassandra roles with LOGIN=true for each Entra ID user before the switch. "
             "The role name should match the preferred_username from the JWT.")

# ══════════════════════════════════════════════════════════════════
# 24. TESTING
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(24, "Testing Strategy", "Unit tests, integration tests, and manual verification")

pdf.sub_header("Unit Tests (18 Passing)")
pdf.body_text(
    "The unit test suite generates a local RSA key pair to create and sign JWT tokens "
    "without any network calls. This enables fast, deterministic testing of: all claim "
    "validation rules, signature verification, key rotation, cache behavior, "
    "and error handling."
)

pdf.bullet_list([
    "Valid token with all claims: verifies end-to-end authentication flow",
    "Expired token: verifies exp claim checking with clock skew tolerance",
    "Wrong audience: verifies aud claim must match configured client_id",
    "Wrong issuer: verifies iss must match configured tenant_id",
    "Tampered payload: verifies signature check catches modifications",
    "Wrong signing key: verifies only Entra ID keys are accepted",
    "Principal name priority: tests 5-level fallback (preferred_username > upn > email > sub > oid)",
    "Claims cache: verifies groups + roles are cached and retrievable",
    "System property config: verifies JVM -D flag configuration",
    "Properties file config: verifies entra-id.properties loading",
    "Empty claims: verifies graceful handling of tokens without groups/roles",
])

pdf.sub_header("Integration Testing Recommendations")
pdf.bullet_list([
    "Test with a real Entra ID tenant and app registration",
    "Test client credentials, managed identity, and interactive flows end-to-end",
    "Test group claims with actual security groups assigned to users",
    "Test token expiry and automatic refresh behavior",
    "Test rolling restart with mixed old/new nodes during migration",
    "Performance benchmark: token validation latency (target: < 1ms for cached keys)",
])

# ══════════════════════════════════════════════════════════════════
# 25. PRODUCTION ARCHITECTURE
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(25, "Production Deployment Architecture",
                   "Complete component diagram for service providers")

pdf.sub_header("Architecture Diagram")
pdf.code_block(
    "+============================================================================+\n"
    "|                        MICROSOFT ENTRA ID (Cloud)                           |\n"
    "|                                                                             |\n"
    "|   Token Endpoint    |    JWKS Endpoint    |    Conditional Access Policies   |\n"
    "|   Audit Logs        |    Group Management |    App Registrations             |\n"
    "+============================================================================+\n"
    "          |                       |                        |\n"
    "     (1) Token              (3) JWKS Keys            (audit logs)\n"
    "          |                       |                        |\n"
    "   +------v---------+    +-------v----------+    +--------v-------+\n"
    "   | APPLICATION    |    | CASSANDRA CLUSTER |    | AZURE PLATFORM |\n"
    "   | TIER           |    |                   |    |                |\n"
    "   | Java / C# /    |--->| EntraIdAuth-      |    | Key Vault      |\n"
    "   | Python apps    | (2)| enticator         |    | (secrets)      |\n"
    "   | + MSAL         |SASL| EntraIdToken-     |    |                |\n"
    "   | + Driver Plugin|    | Validator         |    | Managed        |\n"
    "   | + CQLSH        |    | EntraIdAuthorizer |    | Identity       |\n"
    "   |                |    |                   |    | (auto tokens)  |\n"
    "   +----------------+    | system_auth.      |    |                |\n"
    "                         | entra_group_roles |    | Azure Monitor  |\n"
    "                         +-------------------+    | (alerts)       |\n"
    "                                                  +----------------+\n"
    "\n"
    "(1) MSAL acquires JWT token from Entra ID\n"
    "(2) Driver sends JWT via SASL PLAIN to Cassandra\n"
    "(3) Cassandra fetches JWKS keys to validate JWT signatures (cached 24h)",
    "Production Architecture"
)

pdf.sub_header("Deployment Checklist")
pdf.numbered_list([
    "Azure: App registration created with correct tenant_id and client_id",
    "Azure: App roles defined (CassandraAdmin, CassandraReader, CassandraWriter)",
    "Azure: Group claims configured in token configuration",
    "Azure: Security groups created and members assigned",
    "Azure: Conditional Access policy applied (if using MFA)",
    "Cassandra: Plugin JAR deployed to all nodes in lib/",
    "Cassandra: entra-id.properties configured with tenant_id and client_id",
    "Cassandra: cassandra.yaml updated (authenticator + authorizer)",
    "Cassandra: Roles created matching Entra ID principal names",
    "Cassandra: entra_group_roles table populated",
    "Client: Driver plugins installed (Maven/NuGet/pip)",
    "Client: Application code updated to use MSAL auth providers",
    "Network: TLS enabled on native transport (port 9142)",
    "Monitoring: Azure sign-in log alerts configured",
])

# ══════════════════════════════════════════════════════════════════
# 26. SUMMARY
# ══════════════════════════════════════════════════════════════════
pdf.add_page()
pdf.section_header(26, "Summary & Next Steps")

pdf.sub_header("What We Built")
pdf.bullet_list([
    "Enterprise-grade Microsoft Entra ID authentication for Apache Cassandra 4.1.x",
    "Three server-side Java classes: EntraIdAuthenticator, EntraIdTokenValidator, EntraIdAuthorizer",
    "Zero external dependencies on the server side (JDK crypto + Jackson only)",
    "Drop-in plugin JAR deployment (no Cassandra source modification needed)",
    "Group-based authorization via entra_group_roles mapping table",
    "Pre-built driver plugins for Java 3.x, Java 4.x, C# .NET, and Python",
    "Native CQLSH integration with Entra ID support",
    "Comprehensive documentation: Design, Azure Setup, Developer Guide, User Guide",
    "18 unit tests passing with 100% coverage of critical paths",
])

pdf.sub_header("Key Metrics")
pdf.table(
    ["Metric", "Value"],
    [
        ["Server-side lines of code", "~1,074"],
        ["External dependencies (server)", "0 (JDK + Jackson only)"],
        ["Unit tests", "18 (all passing)"],
        ["Supported drivers", "5 (Java 3.x, 4.x, C#, Python, CQLSH)"],
        ["Auth flows supported", "5 (Client Creds, Managed ID, Interactive, Device Code, ROPC)"],
        ["JWKS cache TTL", "24 hours"],
        ["Clock skew tolerance", "5 minutes"],
        ["Cassandra version", "4.1.x"],
        ["Java target", "8+"],
    ],
    [55, 80]
)

pdf.sub_header("Next Steps")
pdf.numbered_list([
    "Complete integration testing with a real Microsoft Entra ID tenant",
    "Performance benchmarking: measure token validation latency under load",
    "Publish plugin JARs and driver packages to Maven Central / NuGet / PyPI",
    "Create Helm chart for Kubernetes deployment with managed identity",
    "Submit for Apache Cassandra community review and feedback",
    "Explore multi-tenant support (multiple app registrations per cluster)",
    "Add certificate-based authentication as alternative to client secrets",
])

pdf.sub_header("Resources")
pdf.bullet_list([
    "DESIGN.md - Complete architectural design document",
    "AZURE-SETUP-GUIDE.md - Step-by-step Azure Portal configuration",
    "DEVELOPER-GUIDE.md - Implementation details and build instructions",
    "USER-GUIDE.md - End-user setup and configuration guide",
    "CONNECTION-EXAMPLES.md - Code examples for all supported drivers",
])

# ── Save ──────────────────────────────────────────────────────────
output_dir = os.path.dirname(os.path.abspath(__file__))
pdf_path = os.path.join(output_dir, "Cassandra_EntraID_Auth.pdf")
pdf.output(pdf_path)
print(f"PDF saved: {pdf_path}")
print(f"   Pages: {pdf.page_no()}")
file_size = os.path.getsize(pdf_path)
print(f"   Size: {file_size / 1024:.1f} KB")

#!/usr/bin/env python3
"""
Generate a comprehensive PowerPoint presentation about
Microsoft Entra ID Authentication for Apache Cassandra.

Usage:
    python3 generate_presentation.py

Output:
    Cassandra_EntraID_Auth.pptx   (in the same directory)
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.chart import XL_CHART_TYPE
import os

# ── Brand colours ──────────────────────────────────────────────────
AZURE_BLUE     = RGBColor(0x00, 0x78, 0xD4)
DARK_BLUE      = RGBColor(0x00, 0x2B, 0x5C)
MID_BLUE       = RGBColor(0x00, 0x63, 0xB1)
LIGHT_BLUE     = RGBColor(0xDE, 0xEC, 0xF9)
ACCENT_GREEN   = RGBColor(0x10, 0x7C, 0x10)
ACCENT_ORANGE  = RGBColor(0xFF, 0x8C, 0x00)
ACCENT_RED     = RGBColor(0xD1, 0x34, 0x38)
WHITE          = RGBColor(0xFF, 0xFF, 0xFF)
BLACK          = RGBColor(0x00, 0x00, 0x00)
GRAY           = RGBColor(0x60, 0x60, 0x60)
LIGHT_GRAY     = RGBColor(0xF2, 0xF2, 0xF2)
CASSANDRA_TEAL = RGBColor(0x1E, 0x88, 0xA8)

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)

SLD_W = prs.slide_width
SLD_H = prs.slide_height

# ── Helpers ────────────────────────────────────────────────────────

def add_background(slide, color):
    """Set slide background colour."""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_shape(slide, left, top, width, height, fill_color, border_color=None, border_width=Pt(1)):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = border_width
    else:
        shape.line.fill.background()
    return shape

def add_rect(slide, left, top, width, height, fill_color, border_color=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape

def add_arrow(slide, left, top, width, height, fill_color):
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape

def add_down_arrow(slide, left, top, width, height, fill_color):
    shape = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape

def add_oval(slide, left, top, width, height, fill_color, border_color=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(2)
    else:
        shape.line.fill.background()
    return shape

def set_text(shape, text, font_size=14, bold=False, color=BLACK, alignment=PP_ALIGN.CENTER):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = alignment
    tf.auto_size = None

def add_text_box(slide, left, top, width, height, text, font_size=14, bold=False,
                 color=BLACK, alignment=PP_ALIGN.LEFT):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = alignment
    return txBox

def add_bullet_list(slide, left, top, width, height, items, font_size=14, color=BLACK):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = item
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.level = 0
        p.space_before = Pt(4)
        p.space_after = Pt(4)
        # Bullet char
        pPr = p._pPr
        if pPr is None:
            from pptx.oxml.ns import qn
            pPr = p._p.get_or_add_pPr()
        from pptx.oxml.ns import qn
        buChar = pPr.makeelement(qn('a:buChar'), {'char': '●'})
        # remove existing buNone if present
        for child in list(pPr):
            if child.tag.endswith('buNone') or child.tag.endswith('buChar'):
                pPr.remove(child)
        pPr.append(buChar)
    return txBox

def add_top_bar(slide, title_text, subtitle_text=None):
    """Add a coloured header bar to a content slide."""
    bar = add_rect(slide, Inches(0), Inches(0), SLD_W, Inches(1.2), DARK_BLUE)
    set_text(bar, "", 1)  # clear default
    add_text_box(slide, Inches(0.6), Inches(0.15), Inches(10), Inches(0.7),
                 title_text, 32, bold=True, color=WHITE)
    if subtitle_text:
        add_text_box(slide, Inches(0.6), Inches(0.75), Inches(10), Inches(0.4),
                     subtitle_text, 16, color=LIGHT_BLUE)
    # thin accent line under bar
    add_rect(slide, Inches(0), Inches(1.2), SLD_W, Inches(0.05), AZURE_BLUE)

def add_slide_number(slide, num, total):
    add_text_box(slide, Inches(12.3), Inches(7.05), Inches(0.9), Inches(0.35),
                 f"{num}/{total}", 10, color=GRAY, alignment=PP_ALIGN.RIGHT)

def add_footer(slide):
    add_text_box(slide, Inches(0.5), Inches(7.05), Inches(6), Inches(0.35),
                 "Microsoft Entra ID Authentication for Apache Cassandra  |  Confidential",
                 9, color=GRAY)

# ── Count total slides for numbering ──────────────────────────────
TOTAL_SLIDES = 32

# ══════════════════════════════════════════════════════════════════
# SLIDE  1 — TITLE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
add_background(slide, DARK_BLUE)

# Large title
add_text_box(slide, Inches(1), Inches(1.5), Inches(11), Inches(1.5),
             "Microsoft Entra ID Authentication\n& Authorization for Apache Cassandra",
             42, bold=True, color=WHITE, alignment=PP_ALIGN.LEFT)

# Subtitle
add_text_box(slide, Inches(1), Inches(3.3), Inches(9), Inches(0.7),
             "Enterprise-Grade Identity Integration for Cassandra Service Providers",
             22, color=LIGHT_BLUE, alignment=PP_ALIGN.LEFT)

# Accent line
add_rect(slide, Inches(1), Inches(4.2), Inches(3), Inches(0.06), AZURE_BLUE)

# Author & date
add_text_box(slide, Inches(1), Inches(4.6), Inches(6), Inches(1.2),
             "Sachin Gupta  |  March 2026\nApache Cassandra 4.1.x\nDraft — v1.0",
             16, color=WHITE, alignment=PP_ALIGN.LEFT)

# Decorative boxes
add_shape(slide, Inches(10), Inches(4.8), Inches(2.5), Inches(2), AZURE_BLUE)
set_text(slide.shapes[-1], "🔒\nJWT + MSAL\nZero External Deps", 14, True, WHITE)

add_slide_number(slide, 1, TOTAL_SLIDES)

# ══════════════════════════════════════════════════════════════════
# SLIDE  2 — AGENDA
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Agenda")

agenda_left = [
    "1.  Current Cassandra Auth — How It Works",
    "2.  Challenges with Password-Based Auth",
    "3.  Microsoft Entra ID — Overview",
    "4.  Solution Architecture",
    "5.  MSAL — Microsoft Authentication Library",
    "6.  MSAL on Client Side — Token Acquisition",
    "7.  MSAL on Server Side — JWT Validation",
    "8.  Authentication Data Flow",
]
agenda_right = [
    " 9.   Authorization & Group Mapping",
    "10.  Azure Portal — Complete Setup",
    "11.  Server-Side: Plugin JAR & Source",
    "12.  Cassandra Configuration",
    "13.  Client Drivers — Java / C# / Python",
    "14.  CQLSH Integration",
    "15.  Security Considerations",
    "16.  Deployment & Summary",
]

add_bullet_list(slide, Inches(0.8), Inches(1.6), Inches(5.5), Inches(5.5),
                agenda_left, 17, DARK_BLUE)
add_bullet_list(slide, Inches(6.8), Inches(1.6), Inches(5.5), Inches(5.5),
                agenda_right, 17, DARK_BLUE)
add_slide_number(slide, 2, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  3 — CURRENT CASSANDRA AUTH
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Current Cassandra Authentication", "How PasswordAuthenticator works today")

# Client box
c = add_shape(slide, Inches(0.8), Inches(2), Inches(2.5), Inches(1.5), LIGHT_BLUE, AZURE_BLUE)
set_text(c, "Client Application\n(cqlsh / driver)", 14, True, DARK_BLUE)

# Arrow
a1 = add_arrow(slide, Inches(3.5), Inches(2.4), Inches(1.5), Inches(0.6), AZURE_BLUE)
set_text(a1, "PLAIN", 10, True, WHITE)

# Cassandra box
s = add_shape(slide, Inches(5.2), Inches(2), Inches(2.8), Inches(1.5), CASSANDRA_TEAL)
set_text(s, "Cassandra Node\nPasswordAuthenticator", 14, True, WHITE)

# Arrow to system_auth
a2 = add_arrow(slide, Inches(8.2), Inches(2.4), Inches(1.5), Inches(0.6), CASSANDRA_TEAL)
set_text(a2, "bcrypt", 10, True, WHITE)

# DB box
d = add_shape(slide, Inches(9.9), Inches(2), Inches(2.5), Inches(1.5), DARK_BLUE)
set_text(d, "system_auth.roles\n(hashed passwords)", 14, True, WHITE)

# Description bullets
items = [
    "Client sends username + password via SASL PLAIN mechanism",
    "Cassandra computes bcrypt hash and compares with system_auth.roles",
    "CassandraAuthorizer checks system_auth.role_permissions for access control",
    "Each Cassandra cluster maintains its own isolated user database",
    "No integration with corporate identity providers (LDAP/AD/Entra ID)",
]
add_bullet_list(slide, Inches(0.8), Inches(4.2), Inches(11.5), Inches(3), items, 15, GRAY)
add_slide_number(slide, 3, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  4 — CHALLENGES
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Challenges with Password-Based Authentication")

challenges = [
    ("No Centralized Identity", "Each cluster has its own user DB.\nNo single source of truth.", ACCENT_RED),
    ("No MFA / Conditional Access", "Password-only auth cannot enforce\nmulti-factor or device policies.", ACCENT_RED),
    ("Credential Rotation Burden", "Passwords must be rotated manually\nacross all clients and nodes.", ACCENT_ORANGE),
    ("No Group-Based Access", "Permissions granted per-user.\nNo automatic mapping from AD groups.", ACCENT_ORANGE),
    ("Audit / Compliance Gaps", "No integration with corporate\nSIEM/audit log systems.", ACCENT_RED),
    ("No SSO Experience", "Users must maintain separate\nCassandra credentials.", ACCENT_ORANGE),
]

for i, (title, desc, color) in enumerate(challenges):
    col = i % 3
    row = i // 3
    left = Inches(0.8 + col * 4.1)
    top = Inches(1.6 + row * 2.7)
    box = add_shape(slide, left, top, Inches(3.7), Inches(2.2), LIGHT_GRAY, color, Pt(2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = color
    p.alignment = PP_ALIGN.CENTER
    p2 = tf.add_paragraph()
    p2.text = "\n" + desc
    p2.font.size = Pt(13)
    p2.font.color.rgb = GRAY
    p2.alignment = PP_ALIGN.CENTER

add_slide_number(slide, 4, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  5 — ENTRA ID OVERVIEW
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Microsoft Entra ID — Overview", "Formerly Azure Active Directory (Azure AD)")

features = [
    ("Cloud Identity Provider", "Manages users, groups, and service\nprincipals for your organization"),
    ("OAuth 2.0 / OpenID Connect", "Issues JWT access tokens using\nindustry-standard protocols"),
    ("App Registrations", "Each app (like Cassandra) gets a\nclient_id and tenant_id"),
    ("Groups & App Roles", "Organize users into groups; assign\napp-specific roles"),
    ("Conditional Access", "Enforce MFA, device compliance,\nlocation-based policies"),
    ("Managed Identities", "Azure VMs/AKS get automatic tokens\nwithout managing secrets"),
]

for i, (title, desc) in enumerate(features):
    col = i % 3
    row = i // 3
    left = Inches(0.8 + col * 4.1)
    top = Inches(1.6 + row * 2.7)
    box = add_shape(slide, left, top, Inches(3.7), Inches(2.2), LIGHT_BLUE, AZURE_BLUE, Pt(1))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = DARK_BLUE
    p.alignment = PP_ALIGN.CENTER
    p2 = tf.add_paragraph()
    p2.text = "\n" + desc
    p2.font.size = Pt(13)
    p2.font.color.rgb = GRAY
    p2.alignment = PP_ALIGN.CENTER

add_slide_number(slide, 5, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  6 — SOLUTION ARCHITECTURE (HIGH LEVEL)
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Solution Architecture — High Level", "End-to-end authentication & authorization flow")

# --- Entra ID Cloud box ---
entra = add_shape(slide, Inches(4.5), Inches(1.6), Inches(4.2), Inches(1.4), AZURE_BLUE)
set_text(entra, "Microsoft Entra ID\n(Token Issuer + JWKS Publisher)", 15, True, WHITE)

# --- Client Side ---
cbox = add_shape(slide, Inches(0.5), Inches(3.8), Inches(3.5), Inches(3), LIGHT_BLUE, AZURE_BLUE)
tf = cbox.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "CLIENT SIDE"; p.font.size = Pt(14); p.font.bold = True; p.font.color.rgb = DARK_BLUE; p.alignment = PP_ALIGN.CENTER
for line in ["\nApplication + Driver", "MSAL Library (msal4j,", "MSAL.NET, msal-python)", "\nAcquires JWT token", "Sends via SASL PLAIN"]:
    p2 = tf.add_paragraph(); p2.text = line; p2.font.size = Pt(12); p2.font.color.rgb = DARK_BLUE; p2.alignment = PP_ALIGN.CENTER

# --- Server Side ---
sbox = add_shape(slide, Inches(9), Inches(3.8), Inches(3.8), Inches(3), CASSANDRA_TEAL)
tf = sbox.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "SERVER SIDE (Cassandra)"; p.font.size = Pt(14); p.font.bold = True; p.font.color.rgb = WHITE; p.alignment = PP_ALIGN.CENTER
for line in ["\nEntraIdAuthenticator", "EntraIdTokenValidator", "EntraIdAuthorizer", "\nValidates JWT + RS256", "Group → Role mapping"]:
    p2 = tf.add_paragraph(); p2.text = line; p2.font.size = Pt(12); p2.font.color.rgb = WHITE; p2.alignment = PP_ALIGN.CENTER

# Arrows: Client ↔ Entra ID
a_up = add_shape(slide, Inches(2.3), Inches(3.1), Inches(2.5), Inches(0.5), AZURE_BLUE)
set_text(a_up, "① MSAL → Get JWT Token", 10, True, WHITE)

# Client → Server
a_mid = add_arrow(slide, Inches(4.2), Inches(5), Inches(4.5), Inches(0.5), MID_BLUE)
set_text(a_mid, "② SASL PLAIN (username + JWT)", 10, True, WHITE)

# Server → Entra ID (JWKS)
a_jwks = add_shape(slide, Inches(8.5), Inches(3.1), Inches(2.5), Inches(0.5), CASSANDRA_TEAL)
set_text(a_jwks, "③ Fetch JWKS Keys", 10, True, WHITE)

add_slide_number(slide, 6, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  7 — WHAT IS MSAL
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "MSAL — Microsoft Authentication Library", "The foundation for acquiring Entra ID tokens")

add_text_box(slide, Inches(0.8), Inches(1.5), Inches(11.5), Inches(0.8),
             "MSAL is Microsoft's official library for acquiring OAuth 2.0 tokens from the Microsoft Identity Platform.\n"
             "It handles the complexity of token caching, silent refresh, and multiple authentication flows.",
             15, color=GRAY)

headers = ["Feature", "MSAL4J (Java)", "MSAL.NET (C#)", "msal-python"]
rows = [
    ["Token caching", "✅ In-memory + serialisable", "✅ In-memory + serialisable", "✅ In-memory + serialisable"],
    ["Silent refresh", "✅ Automatic", "✅ Automatic", "✅ Automatic"],
    ["Client credentials", "✅ Secret & certificate", "✅ Secret & certificate", "✅ Secret & certificate"],
    ["Managed Identity", "✅ System & User-assigned", "✅ System & User-assigned", "✅ System & User-assigned"],
    ["Interactive / Device code", "✅", "✅", "✅"],
    ["ROPC (username/password)", "✅", "✅", "✅"],
    ["Confidential client", "✅", "✅", "✅"],
    ["Maven / NuGet / pip", "com.microsoft.azure:msal4j", "Microsoft.Identity.Client", "msal"],
]

# Draw table
table_left = Inches(0.8)
table_top = Inches(2.6)
col_widths = [Inches(2.5), Inches(3.2), Inches(3.2), Inches(3.2)]
row_height = Inches(0.45)

# Header row
x = table_left
for j, h in enumerate(headers):
    cell = add_rect(slide, x, table_top, col_widths[j], row_height, DARK_BLUE)
    set_text(cell, h, 12, True, WHITE)
    x += col_widths[j]

# Data rows
for i, row in enumerate(rows):
    x = table_left
    bg = LIGHT_GRAY if i % 2 == 0 else WHITE
    for j, val in enumerate(row):
        cell = add_rect(slide, x, table_top + row_height * (i + 1), col_widths[j], row_height, bg, RGBColor(0xDD, 0xDD, 0xDD))
        set_text(cell, val, 11, False, BLACK)
        x += col_widths[j]

add_slide_number(slide, 7, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  8 — MSAL CLIENT SIDE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "MSAL on Client Side — Token Acquisition", "How client applications obtain JWT tokens")

# Flow boxes
flows = [
    ("Client Credentials\n(Service-to-Service)", "● App authenticates with client_id + secret\n● No user context\n● Best for: backend services, batch jobs\n● Scope: api://{client_id}/.default", AZURE_BLUE),
    ("Managed Identity\n(Azure VM/AKS)", "● Azure provides tokens automatically\n● No secrets to manage\n● Best for: Azure-hosted workloads\n● Uses IMDS endpoint (169.254.169.254)", ACCENT_GREEN),
    ("Interactive / Device Code\n(User Auth)", "● User signs in via browser / device code\n● Supports MFA & Conditional Access\n● Best for: developer tools, CQLSH\n● Provides user identity + group claims", MID_BLUE),
    ("ROPC\n(Username/Password)", "● Direct username + password grant\n● No MFA support\n● Best for: legacy migration only\n● Not recommended for production", ACCENT_ORANGE),
]

for i, (title, desc, color) in enumerate(flows):
    col = i % 2
    row = i // 2
    left = Inches(0.6 + col * 6.3)
    top = Inches(1.5 + row * 2.9)
    box = add_shape(slide, left, top, Inches(5.8), Inches(2.5), LIGHT_GRAY, color, Pt(2))
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title; p.font.size = Pt(16); p.font.bold = True; p.font.color.rgb = color; p.alignment = PP_ALIGN.LEFT
    p2 = tf.add_paragraph(); p2.text = "\n" + desc; p2.font.size = Pt(13); p2.font.color.rgb = GRAY; p2.alignment = PP_ALIGN.LEFT

add_slide_number(slide, 8, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE  9 — MSAL CLIENT CODE EXAMPLES
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "MSAL Client Code — All Languages", "Token acquisition code snippets")

# Java example
java_code = (
    "// Java — MSAL4J Client Credentials\n"
    "ConfidentialClientApplication app = ConfidentialClientApplication\n"
    "    .builder(CLIENT_ID, ClientCredentialFactory\n"
    "        .createFromSecret(CLIENT_SECRET))\n"
    "    .authority(\"https://login.microsoftonline.com/\" + TENANT_ID)\n"
    "    .build();\n"
    "String token = app.acquireToken(\n"
    "    ClientCredentialParameters.builder(\n"
    "        Collections.singleton(\"api://\" + CLIENT_ID + \"/.default\"))\n"
    "    .build()).get().accessToken();"
)

csharp_code = (
    "// C# — MSAL.NET Client Credentials\n"
    "var app = ConfidentialClientApplicationBuilder\n"
    "    .Create(clientId)\n"
    "    .WithClientSecret(clientSecret)\n"
    "    .WithAuthority($\"https://login.microsoftonline.com/{tenantId}\")\n"
    "    .Build();\n"
    "var result = await app.AcquireTokenForClient(\n"
    "    new[] { $\"api://{clientId}/.default\" }).ExecuteAsync();\n"
    "string token = result.AccessToken;"
)

python_code = (
    "# Python — msal\n"
    "app = msal.ConfidentialClientApplication(\n"
    "    client_id, authority=f\"https://login.microsoftonline.com/{tenant_id}\",\n"
    "    client_credential=client_secret)\n"
    "result = app.acquire_token_for_client(\n"
    "    scopes=[f\"api://{client_id}/.default\"])\n"
    "token = result['access_token']"
)

examples = [("Java (MSAL4J)", java_code), ("C# (MSAL.NET)", csharp_code), ("Python (msal)", python_code)]
for i, (title, code) in enumerate(examples):
    left = Inches(0.5 + i * 4.2)
    # Title
    add_text_box(slide, left, Inches(1.5), Inches(3.8), Inches(0.4), title, 14, True, AZURE_BLUE)
    # Code box
    box = add_shape(slide, left, Inches(1.95), Inches(3.8), Inches(5.2), RGBColor(0x1E, 0x1E, 0x2E))
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = code; p.font.size = Pt(9); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT
    p.font.name = "Consolas"

add_slide_number(slide, 9, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 10 — MSAL SERVER SIDE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "MSAL on Server Side — JWT Validation", "How Cassandra validates tokens WITHOUT MSAL at runtime")

add_text_box(slide, Inches(0.8), Inches(1.5), Inches(11.5), Inches(0.6),
             "Key Insight: The Cassandra server does NOT use MSAL at runtime. MSAL is client-only.\n"
             "The server validates tokens using JDK crypto — zero external dependencies.",
             15, bold=True, color=ACCENT_RED)

# Validation pipeline
steps = [
    ("1. Parse JWT", "Split into\nheader.payload.signature\nDecode base64url"),
    ("2. Read Header", "Extract 'kid' (key ID)\nVerify 'alg' = RS256"),
    ("3. Fetch JWKS", "GET login.microsoftonline.com\n/{tenant}/discovery/v2.0/keys\nCache 24 hours"),
    ("4. Verify Signature", "SHA256withRSA\nusing java.security.Signature\nJDK built-in"),
    ("5. Validate Claims", "iss = tenant issuer\naud = client_id\nexp > now\nnbf < now"),
    ("6. Extract Identity", "preferred_username\noid, upn, groups\nroles → claimsCache"),
]

for i, (title, desc) in enumerate(steps):
    left = Inches(0.4 + i * 2.1)
    top = Inches(2.7)
    box = add_shape(slide, left, top, Inches(1.9), Inches(2.8), LIGHT_BLUE, AZURE_BLUE)
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title; p.font.size = Pt(13); p.font.bold = True; p.font.color.rgb = DARK_BLUE; p.alignment = PP_ALIGN.CENTER
    p2 = tf.add_paragraph(); p2.text = "\n" + desc; p2.font.size = Pt(11); p2.font.color.rgb = GRAY; p2.alignment = PP_ALIGN.CENTER
    # Arrow between steps
    if i < len(steps) - 1:
        add_arrow(slide, left + Inches(1.95), top + Inches(1.2), Inches(0.12), Inches(0.35), AZURE_BLUE)

key_points = [
    "java.security.Signature (SHA256withRSA) — JDK built-in, no BouncyCastle needed",
    "java.security.KeyFactory (RSA) — constructs PublicKey from JWKS modulus + exponent",
    "java.util.Base64.getUrlDecoder() — standard JWT base64url decoding",
    "com.fasterxml.jackson.databind — already in Cassandra's classpath (JSON parsing)",
]
add_bullet_list(slide, Inches(0.5), Inches(5.8), Inches(12), Inches(1.5), key_points, 13, GRAY)
add_slide_number(slide, 10, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 11 — AUTHENTICATION DATA FLOW
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Authentication Data Flow", "Step-by-step token lifecycle")

# Swimlane labels
add_text_box(slide, Inches(0.2), Inches(1.6), Inches(1.8), Inches(0.4), "Client App", 14, True, DARK_BLUE)
add_text_box(slide, Inches(0.2), Inches(3.0), Inches(1.8), Inches(0.4), "Entra ID", 14, True, AZURE_BLUE)
add_text_box(slide, Inches(0.2), Inches(4.5), Inches(1.8), Inches(0.4), "Cassandra", 14, True, CASSANDRA_TEAL)
add_text_box(slide, Inches(0.2), Inches(5.9), Inches(1.8), Inches(0.4), "JWKS Endpoint", 14, True, ACCENT_GREEN)

# Swimlane lines
for y in [Inches(2.0), Inches(3.4), Inches(4.9), Inches(6.3)]:
    add_rect(slide, Inches(2.2), y, Inches(10.5), Inches(0.02), LIGHT_GRAY)

# Steps (positioned as sequence diagram)
step_data = [
    (Inches(2.5), Inches(1.5), Inches(2.5), Inches(0.65), "① App calls MSAL\nacquireToken(scope)", LIGHT_BLUE, DARK_BLUE),
    (Inches(5.3), Inches(2.8), Inches(2.8), Inches(0.65), "② MSAL sends OAuth request\n(client credentials / auth code)", LIGHT_BLUE, AZURE_BLUE),
    (Inches(5.3), Inches(3.6), Inches(2.8), Inches(0.65), "③ Entra ID returns\nJWT access token", LIGHT_BLUE, AZURE_BLUE),
    (Inches(2.5), Inches(2.2), Inches(2.5), Inches(0.65), "④ MSAL caches token,\nreturns to app", LIGHT_BLUE, DARK_BLUE),
    (Inches(8.5), Inches(4.3), Inches(3.2), Inches(0.65), "⑤ Driver sends SASL PLAIN\n(NUL + user + NUL + JWT)", CASSANDRA_TEAL, WHITE),
    (Inches(8.5), Inches(5.7), Inches(3.2), Inches(0.65), "⑥ Authenticator fetches\nJWKS public keys (cached 24h)", RGBColor(0xC8, 0xE6, 0xC9), DARK_BLUE),
    (Inches(2.5), Inches(5.0), Inches(5.5), Inches(0.65), "⑦ Verify RS256 signature → validate claims → cache groups → AuthenticatedUser", CASSANDRA_TEAL, WHITE),
]

for (l, t, w, h, txt, bg, fg) in step_data:
    box = add_shape(slide, l, t, w, h, bg, None)
    set_text(box, txt, 10, False, fg)

add_slide_number(slide, 11, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 12 — AUTHORIZATION FLOW
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Authorization & Group-to-Role Mapping", "How Entra ID groups map to Cassandra permissions")

# Flow diagram
boxes = [
    (Inches(0.5), Inches(1.8), "User authenticates\nwith JWT", AZURE_BLUE, WHITE),
    (Inches(0.5), Inches(3.4), "Claims cached:\ngroups: [g1, g2]\nroles: [r1]", LIGHT_BLUE, DARK_BLUE),
    (Inches(4.0), Inches(1.8), "EntraIdAuthorizer.\nauthorize(user, resource)", CASSANDRA_TEAL, WHITE),
    (Inches(4.0), Inches(3.4), "Step 1:\nsuper.authorize()\nstandard role_permissions", LIGHT_BLUE, DARK_BLUE),
    (Inches(7.5), Inches(1.8), "Step 2: For each\ngroup_id → lookup\nentra_group_roles", MID_BLUE, WHITE),
    (Inches(7.5), Inches(3.4), "Step 3: For each\nmapped role →\nget role_permissions", MID_BLUE, WHITE),
    (Inches(10.5), Inches(2.6), "UNION of all\npermissions\n= final access", ACCENT_GREEN, WHITE),
]

for (l, t, title, bg, fg) in boxes:
    box = add_shape(slide, l, t, Inches(2.8), Inches(1.2), bg, None)
    set_text(box, title, 12, True, fg)

# Table schema
add_text_box(slide, Inches(0.5), Inches(5.0), Inches(12), Inches(0.4),
             "system_auth.entra_group_roles — Mapping Table", 16, True, DARK_BLUE)

schema_rows = [
    ["CREATE TABLE system_auth.entra_group_roles ("],
    ["    group_id       text,      -- Entra ID group UUID or app role name"],
    ["    cassandra_role text,      -- Target Cassandra role name"],
    ["    PRIMARY KEY (group_id, cassandra_role)"],
    [");"],
]
code_text = "\n".join([r[0] for r in schema_rows])
code_box = add_shape(slide, Inches(0.5), Inches(5.45), Inches(8), Inches(1.7), RGBColor(0x1E, 0x1E, 0x2E))
tf = code_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = code_text; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# Example
example_box = add_shape(slide, Inches(8.8), Inches(5.45), Inches(4), Inches(1.7), LIGHT_BLUE, AZURE_BLUE)
set_text(example_box,
         "Example:\n'aad-group-uuid-1' → 'db_readers'\n'aad-group-uuid-2' → 'db_writers'\n'CassandraAdmin' → 'cassandra_superuser'",
         12, False, DARK_BLUE)

add_slide_number(slide, 12, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 13 — AZURE PORTAL SETUP OVERVIEW
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Azure Portal — App Registration Setup", "Complete walkthrough for service providers")

steps = [
    ("Step 1", "Register Application", "Entra ID → App registrations\n→ New registration\nName: 'Apache Cassandra Cluster'\nSingle tenant"),
    ("Step 2", "Expose an API", "Set Application ID URI:\napi://{client-id}\nCreates .default scope"),
    ("Step 3", "Create App Roles", "App registrations → App roles\nAdd: CassandraAdmin,\nCassandraReader, CassandraWriter"),
    ("Step 4", "Configure Group Claims", "Token configuration →\nAdd groups claim →\nSelect 'Security groups'\nEmit as: Group ID"),
    ("Step 5", "Create Client Secret", "Certificates & secrets →\nNew client secret\nNote: save the Value immediately"),
    ("Step 6", "Assign Users & Groups", "Enterprise applications →\nYour app → Users and groups\n→ Add user/group"),
]

for i, (step, title, desc) in enumerate(steps):
    col = i % 3
    row = i // 3
    left = Inches(0.5 + col * 4.2)
    top = Inches(1.5 + row * 2.9)
    box = add_shape(slide, left, top, Inches(3.9), Inches(2.5), WHITE, AZURE_BLUE, Pt(2))
    tf = box.text_frame; tf.word_wrap = True
    # Step number badge
    p = tf.paragraphs[0]; p.text = step; p.font.size = Pt(11); p.font.bold = True; p.font.color.rgb = AZURE_BLUE; p.alignment = PP_ALIGN.LEFT
    p2 = tf.add_paragraph(); p2.text = title; p2.font.size = Pt(15); p2.font.bold = True; p2.font.color.rgb = DARK_BLUE; p2.alignment = PP_ALIGN.LEFT
    p3 = tf.add_paragraph(); p3.text = "\n" + desc; p3.font.size = Pt(12); p3.font.color.rgb = GRAY; p3.alignment = PP_ALIGN.LEFT

add_slide_number(slide, 13, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 14 — AZURE PORTAL: APP REGISTRATION DETAIL
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Azure Portal — App Registration Details", "What to configure and where to find the values")

# Simulated portal screenshot with boxes
portal_bg = add_rect(slide, Inches(0.5), Inches(1.5), Inches(12.3), Inches(5.5), LIGHT_GRAY, RGBColor(0xCC, 0xCC, 0xCC))

# Left nav
nav = add_rect(slide, Inches(0.5), Inches(1.5), Inches(2.5), Inches(5.5), RGBColor(0xF5, 0xF5, 0xF5))
nav_items = ["Overview", "Authentication", "Certificates & secrets", "Token configuration", "API permissions", "Expose an API", "App roles", "Owners"]
y = Inches(1.7)
for item in nav_items:
    add_text_box(slide, Inches(0.6), y, Inches(2.3), Inches(0.35), item, 11, color=MID_BLUE)
    y += Inches(0.4)

# Main content: Overview page
add_text_box(slide, Inches(3.3), Inches(1.7), Inches(5), Inches(0.5),
             "Apache Cassandra Cluster  |  Overview", 18, True, DARK_BLUE)

# Key values table
values = [
    ("Application (client) ID", "6731de76-14a6-49ae-97bc-6eba6914391e", "→ client_id"),
    ("Directory (tenant) ID", "72f988bf-86f1-41af-91ab-2d7cd011db47", "→ tenant_id"),
    ("Application ID URI", "api://6731de76-14a6-49ae-97bc-6eba6914391e", "→ scope prefix"),
    ("Object ID", "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "(internal)"),
]

y = Inches(2.4)
for label, value, note in values:
    add_text_box(slide, Inches(3.5), y, Inches(2.5), Inches(0.4), label, 12, True, GRAY)
    val_box = add_shape(slide, Inches(6.2), y, Inches(4.2), Inches(0.38), WHITE, RGBColor(0xDD, 0xDD, 0xDD))
    set_text(val_box, value, 11, False, BLACK)
    add_text_box(slide, Inches(10.6), y, Inches(2), Inches(0.4), note, 11, True, AZURE_BLUE)
    y += Inches(0.55)

# Callout
callout = add_shape(slide, Inches(3.5), Inches(4.8), Inches(9), Inches(1.8), LIGHT_BLUE, AZURE_BLUE)
set_text(callout,
         "Service Provider Action Items:\n\n"
         "1. Give the Tenant ID and Client ID to customers for their driver configuration\n"
         "2. Create app roles (CassandraAdmin, CassandraReader) for RBAC\n"
         "3. Configure Token → Group Claims to emit security group IDs in JWT\n"
         "4. Create a client secret for each service principal / environment",
         12, False, DARK_BLUE, PP_ALIGN.LEFT)

add_slide_number(slide, 14, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 15 — AZURE PORTAL: TOKEN CONFIG
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Azure Portal — Token & Group Claims Configuration")

# Token config section
add_text_box(slide, Inches(0.5), Inches(1.5), Inches(6), Inches(0.5),
             "Token Configuration → Add Groups Claim", 16, True, DARK_BLUE)

groups_box = add_shape(slide, Inches(0.5), Inches(2.1), Inches(5.8), Inches(3.5), LIGHT_GRAY, AZURE_BLUE)
tf = groups_box.text_frame; tf.word_wrap = True
lines = [
    ("Edit groups claim", True, DARK_BLUE, 14),
    ("\nSelect which groups to include in the token:", False, GRAY, 12),
    ("\n☑  Security groups", False, BLACK, 13),
    ("☐  Directory roles", False, GRAY, 13),
    ("☐  Groups assigned to the application", False, GRAY, 13),
    ("☐  All groups", False, GRAY, 13),
    ("\nCustomize token properties by type:", False, GRAY, 12),
    ("  Access token → Emit groups as: Group ID", False, BLACK, 12),
]
for i, (text, bold, color, size) in enumerate(lines):
    if i == 0:
        p = tf.paragraphs[0]
    else:
        p = tf.add_paragraph()
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = PP_ALIGN.LEFT

# App Roles section
add_text_box(slide, Inches(6.8), Inches(1.5), Inches(6), Inches(0.5),
             "App Roles → Define Custom Roles", 16, True, DARK_BLUE)

roles_box = add_shape(slide, Inches(6.8), Inches(2.1), Inches(5.8), Inches(3.5), LIGHT_GRAY, AZURE_BLUE)
tf = roles_box.text_frame; tf.word_wrap = True
roles_text = [
    ("App roles", True, DARK_BLUE, 14),
    ("\nThese roles appear in the 'roles' claim of the JWT:", False, GRAY, 12),
    ("\nDisplay name        Value              Allowed members", True, BLACK, 11),
    ("─────────────────────────────────────────────", False, GRAY, 9),
    ("Cassandra Admin    CassandraAdmin     Users/Groups", False, BLACK, 11),
    ("Cassandra Reader   CassandraReader    Users/Groups", False, BLACK, 11),
    ("Cassandra Writer   CassandraWriter    Users/Groups", False, BLACK, 11),
    ("\nResult in JWT: \"roles\": [\"CassandraAdmin\"]", True, AZURE_BLUE, 12),
]
for i, (text, bold, color, size) in enumerate(roles_text):
    if i == 0:
        p = tf.paragraphs[0]
    else:
        p = tf.add_paragraph()
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = PP_ALIGN.LEFT

# JWT preview
add_text_box(slide, Inches(0.5), Inches(5.9), Inches(6), Inches(0.4),
             "Resulting JWT Claims (decoded payload):", 14, True, DARK_BLUE)
jwt_preview = (
    '{\n  "iss": "https://login.microsoftonline.com/{tenant}/v2.0",\n'
    '  "aud": "6731de76-14a6-49ae-97bc-6eba6914391e",\n'
    '  "preferred_username": "user@contoso.com",\n'
    '  "groups": ["aad-group-uuid-1", "aad-group-uuid-2"],\n'
    '  "roles": ["CassandraAdmin"],\n'
    '  "exp": 1740000000\n}'
)
jwt_box = add_shape(slide, Inches(0.5), Inches(6.35), Inches(12.3), Inches(1.0), RGBColor(0x1E, 0x1E, 0x2E))
tf = jwt_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = jwt_preview; p.font.size = Pt(10); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

add_slide_number(slide, 15, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 16 — SERVER SIDE: THREE COMPONENTS
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Server-Side Components — Three Java Classes", "Zero external dependencies — JDK crypto + Jackson only")

components = [
    ("EntraIdAuthenticator", "IAuthenticator",
     "● Implements Cassandra's IAuthenticator interface\n"
     "● Returns EntraIdSaslNegotiator for SASL PLAIN\n"
     "● Decodes NUL-separated username + JWT token\n"
     "● Delegates to TokenValidator for JWT validation\n"
     "● Caches claims (groups, roles) in ConcurrentHashMap\n"
     "● Returns AuthenticatedUser(principalName)",
     AZURE_BLUE),
    ("EntraIdTokenValidator", "JWT Engine",
     "● Pure JWT validation — no external libraries\n"
     "● Fetches JWKS from login.microsoftonline.com\n"
     "● Caches RSA public keys for 24 hours\n"
     "● Verifies RS256 signature (SHA256withRSA)\n"
     "● Validates iss, aud, exp, nbf claims\n"
     "● Extracts oid, preferred_username, groups, roles",
     MID_BLUE),
    ("EntraIdAuthorizer", "CassandraAuthorizer+",
     "● Extends CassandraAuthorizer (inherits all standard behavior)\n"
     "● Adds group-based authorization layer\n"
     "● Reads claims from authenticator's cache\n"
     "● Looks up entra_group_roles for each group ID\n"
     "● UNION of direct perms + group-mapped perms\n"
     "● Creates entra_group_roles table on setup()",
     CASSANDRA_TEAL),
]

for i, (name, iface, desc, color) in enumerate(components):
    left = Inches(0.5 + i * 4.2)
    # Header
    hdr = add_shape(slide, left, Inches(1.5), Inches(3.8), Inches(0.7), color)
    set_text(hdr, f"{name}\n({iface})", 13, True, WHITE)
    # Body
    body = add_shape(slide, left, Inches(2.2), Inches(3.8), Inches(4.2), LIGHT_GRAY, color)
    tf = body.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = desc; p.font.size = Pt(12); p.font.color.rgb = DARK_BLUE; p.alignment = PP_ALIGN.LEFT

# Key stat
add_text_box(slide, Inches(0.5), Inches(6.7), Inches(12), Inches(0.5),
             "Total lines of code: ~1,074  |  External dependencies: 0  |  Compiled target: Java 8  |  Tests: 18 passing",
             14, True, AZURE_BLUE, PP_ALIGN.CENTER)

add_slide_number(slide, 16, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 17 — SERVER DEPLOYMENT OPTIONS
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Server Deployment — Plugin JAR vs Source Integration", "Two ways to deploy the server-side components")

# Option A
a_box = add_shape(slide, Inches(0.5), Inches(1.5), Inches(5.8), Inches(5.5), LIGHT_BLUE, ACCENT_GREEN, Pt(3))
tf = a_box.text_frame; tf.word_wrap = True
lines = [
    ("OPTION A — Plugin JAR (Recommended)", True, ACCENT_GREEN, 16),
    ("\nNo Cassandra source modification required!", True, DARK_BLUE, 13),
    ("\nBuild:", True, DARK_BLUE, 13),
    ("  cd server-plugin && mvn clean package", False, BLACK, 12),
    ("\nDeploy:", True, DARK_BLUE, 13),
    ("  cp cassandra-entra-id-auth-1.0.0.jar $CASSANDRA_HOME/lib/", False, BLACK, 12),
    ("\nConfigure (choose one):", True, DARK_BLUE, 13),
    ("  a) conf/entra-id.properties (tenant_id + client_id)", False, BLACK, 12),
    ("  b) JVM: -Dcassandra.entra.tenant_id=...", False, BLACK, 12),
    ("  c) Custom path: -Dcassandra.entra.config=/path", False, BLACK, 12),
    ("\nAdvantages:", True, DARK_BLUE, 13),
    ("  ● Works with stock Cassandra 4.1.x", False, ACCENT_GREEN, 12),
    ("  ● No recompilation of Cassandra source", False, ACCENT_GREEN, 12),
    ("  ● Easy upgrade — just replace the JAR", False, ACCENT_GREEN, 12),
]

for i, (text, bold, color, size) in enumerate(lines):
    if i == 0:
        p = tf.paragraphs[0]
    else:
        p = tf.add_paragraph()
    p.text = text; p.font.size = Pt(size); p.font.bold = bold; p.font.color.rgb = color; p.alignment = PP_ALIGN.LEFT

# Option B
b_box = add_shape(slide, Inches(6.8), Inches(1.5), Inches(5.8), Inches(5.5), LIGHT_GRAY, MID_BLUE, Pt(3))
tf = b_box.text_frame; tf.word_wrap = True
lines = [
    ("OPTION B — Source Integration", True, MID_BLUE, 16),
    ("\nCompile directly into cassandra-all", True, DARK_BLUE, 13),
    ("\nModifications:", True, DARK_BLUE, 13),
    ("  • Config.java: add entra_tenant_id, entra_client_id", False, BLACK, 12),
    ("  • cassandra.yaml: document new fields", False, BLACK, 12),
    ("  • auth/*.java: three new classes + test", False, BLACK, 12),
    ("\nBuild:", True, DARK_BLUE, 13),
    ("  ant jar  (builds entire Cassandra)", False, BLACK, 12),
    ("\nConfigure:", True, DARK_BLUE, 13),
    ("  cassandra.yaml:", False, BLACK, 12),
    ("    entra_tenant_id: YOUR-TENANT-ID", False, BLACK, 12),
    ("    entra_client_id: YOUR-CLIENT-ID", False, BLACK, 12),
    ("\nAdvantages:", True, DARK_BLUE, 13),
    ("  ● Native YAML configuration", False, MID_BLUE, 12),
    ("  ● Single binary deployment", False, MID_BLUE, 12),
]

for i, (text, bold, color, size) in enumerate(lines):
    if i == 0:
        p = tf.paragraphs[0]
    else:
        p = tf.add_paragraph()
    p.text = text; p.font.size = Pt(size); p.font.bold = bold; p.font.color.rgb = color; p.alignment = PP_ALIGN.LEFT

add_slide_number(slide, 17, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 18 — CASSANDRA CONFIGURATION
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Cassandra Configuration", "cassandra.yaml and supporting files")

# cassandra.yaml
add_text_box(slide, Inches(0.5), Inches(1.5), Inches(6), Inches(0.4),
             "cassandra.yaml (required for both deployment options)", 14, True, DARK_BLUE)

yaml_code = (
    "# Authentication — use EntraID JWT tokens\n"
    "authenticator: EntraIdAuthenticator\n"
    "\n"
    "# Authorization — standard + Entra ID group mapping\n"
    "authorizer: EntraIdAuthorizer\n"
    "\n"
    "# Role manager — unchanged\n"
    "role_manager: CassandraRoleManager\n"
    "\n"
    "# Source integration only:\n"
    "# entra_tenant_id: 72f988bf-86f1-41af-91ab-2d7cd011db47\n"
    "# entra_client_id: 6731de76-14a6-49ae-97bc-6eba6914391e"
)
yaml_box = add_shape(slide, Inches(0.5), Inches(2.0), Inches(6), Inches(3.8), RGBColor(0x1E, 0x1E, 0x2E))
tf = yaml_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = yaml_code; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# entra-id.properties
add_text_box(slide, Inches(7), Inches(1.5), Inches(6), Inches(0.4),
             "conf/entra-id.properties  (plugin JAR only)", 14, True, DARK_BLUE)

props_code = (
    "# Microsoft Entra ID Configuration\n"
    "# for Plugin JAR deployment\n"
    "\n"
    "# Your Azure AD Tenant ID (Directory ID)\n"
    "tenant_id=72f988bf-86f1-41af-91ab-2d7cd011db47\n"
    "\n"
    "# Your App Registration's Client ID\n"
    "client_id=6731de76-14a6-49ae-97bc-6eba6914391e"
)
props_box = add_shape(slide, Inches(7), Inches(2.0), Inches(5.8), Inches(2.6), RGBColor(0x1E, 0x1E, 0x2E))
tf = props_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = props_code; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# JVM opts
add_text_box(slide, Inches(7), Inches(4.9), Inches(6), Inches(0.4),
             "jvm-server.options  (alternative for containerised envs)", 14, True, DARK_BLUE)
jvm_code = (
    "# Alternative: JVM system properties\n"
    "-Dcassandra.entra.tenant_id=72f988bf-...\n"
    "-Dcassandra.entra.client_id=6731de76-..."
)
jvm_box = add_shape(slide, Inches(7), Inches(5.4), Inches(5.8), Inches(1.2), RGBColor(0x1E, 0x1E, 0x2E))
tf = jvm_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = jvm_code; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# Config precedence
add_text_box(slide, Inches(0.5), Inches(6.2), Inches(6), Inches(1),
             "Config Precedence (first wins):\n"
             "  1. JVM system properties (-D...)\n"
             "  2. Properties file (conf/entra-id.properties)\n"
             "  3. Custom file (-Dcassandra.entra.config=...)",
             12, False, GRAY)

add_slide_number(slide, 18, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 19 — CLIENT DRIVER: JAVA 3.x
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Client Driver — Java (DataStax Driver 3.x)", "Pre-built plugin or manual integration")

java3_dep = (
    "<!-- Maven dependency -->\n"
    "<dependency>\n"
    "  <groupId>org.apache.cassandra</groupId>\n"
    "  <artifactId>cassandra-entra-id-auth-driver3</artifactId>\n"
    "  <version>1.0.0</version>\n"
    "</dependency>"
)
java3_usage = (
    "// Usage\n"
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
    "Session session = cluster.connect();"
)

add_text_box(slide, Inches(0.5), Inches(1.5), Inches(6), Inches(0.4), "Maven Dependency", 14, True, DARK_BLUE)
dep_box = add_shape(slide, Inches(0.5), Inches(1.95), Inches(5.5), Inches(2.0), RGBColor(0x1E, 0x1E, 0x2E))
tf = dep_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = java3_dep; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

add_text_box(slide, Inches(6.5), Inches(1.5), Inches(6), Inches(0.4), "Application Code", 14, True, DARK_BLUE)
usage_box = add_shape(slide, Inches(6.5), Inches(1.95), Inches(6.3), Inches(3.5), RGBColor(0x1E, 0x1E, 0x2E))
tf = usage_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = java3_usage; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# How it works
items = [
    "EntraIdAuthProvider implements AuthProvider (Driver 3.x API)",
    "Uses MSAL4J ConfidentialClientApplication to acquire JWT tokens from Entra ID",
    "Builds SASL PLAIN response: NUL + preferred_username + NUL + JWT_access_token",
    "Uber JAR (via Maven Shade) includes MSAL4J — no classpath conflicts",
    "Supports: Client Credentials, Managed Identity, Username/Password (ROPC)",
]
add_bullet_list(slide, Inches(0.5), Inches(4.5), Inches(12), Inches(2.5), items, 14, GRAY)

add_slide_number(slide, 19, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 20 — CLIENT DRIVER: JAVA 4.x
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Client Driver — Java (DataStax Driver 4.x)", "Programmatic auth provider for the modern driver")

java4_usage = (
    "// Driver 4.x — Programmatic AuthProvider\n"
    "EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()\n"
    "    .tenantId(\"YOUR-TENANT-ID\")\n"
    "    .clientId(\"YOUR-CLIENT-ID\")\n"
    "    .clientSecret(\"YOUR-SECRET\")\n"
    "    .build();\n"
    "\n"
    "CqlSession session = CqlSession.builder()\n"
    "    .addContactPoint(new InetSocketAddress(\"host\", 9042))\n"
    "    .withAuthProvider(authProvider)\n"
    "    .withLocalDatacenter(\"datacenter1\")\n"
    "    .build();"
)

managed_id = (
    "// Managed Identity (Azure VM / AKS)\n"
    "EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()\n"
    "    .tenantId(\"YOUR-TENANT-ID\")\n"
    "    .clientId(\"YOUR-CLIENT-ID\")\n"
    "    .useManagedIdentity(true)\n"
    "    .build();\n"
    "// No secrets needed — Azure provides tokens!"
)

add_text_box(slide, Inches(0.5), Inches(1.5), Inches(6), Inches(0.4), "Client Credentials Flow", 14, True, DARK_BLUE)
box1 = add_shape(slide, Inches(0.5), Inches(1.95), Inches(6), Inches(3.3), RGBColor(0x1E, 0x1E, 0x2E))
tf = box1.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = java4_usage; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

add_text_box(slide, Inches(7), Inches(1.5), Inches(6), Inches(0.4), "Managed Identity Flow", 14, True, ACCENT_GREEN)
box2 = add_shape(slide, Inches(7), Inches(1.95), Inches(5.8), Inches(2.2), RGBColor(0x1E, 0x1E, 0x2E))
tf = box2.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = managed_id; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# Key differences
diff_items = [
    "Driver 4.x: AuthProvider interface has different method signatures than 3.x",
    "Uses Node-level onMissingChallenge() and Authenticator inner class pattern",
    "Artifact: org.apache.cassandra:cassandra-entra-id-auth-driver4:1.0.0",
    "Internal MSAL4J version shaded to avoid runtime conflicts",
]
add_bullet_list(slide, Inches(0.5), Inches(5.5), Inches(12), Inches(1.8), diff_items, 14, GRAY)

add_slide_number(slide, 20, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 21 — CLIENT DRIVER: C# .NET
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Client Driver — C# (.NET DataStax Driver)", "NuGet package with MSAL.NET integration")

csharp_dep = (
    "<!-- NuGet -->\n"
    "dotnet add package Apache.Cassandra.EntraIdAuth\n"
    "\n"
    "<!-- Or in .csproj -->\n"
    "<PackageReference Include=\"Apache.Cassandra.EntraIdAuth\"\n"
    "                  Version=\"1.0.0\" />"
)
csharp_usage = (
    "// C# — Client Credentials\n"
    "var authProvider = new EntraIdAuthProvider(\n"
    "    tenantId: \"YOUR-TENANT-ID\",\n"
    "    clientId: \"YOUR-CLIENT-ID\",\n"
    "    clientSecret: \"YOUR-SECRET\");\n"
    "\n"
    "var cluster = Cluster.Builder()\n"
    "    .AddContactPoint(\"cassandra-host\")\n"
    "    .WithAuthProvider(authProvider)\n"
    "    .Build();\n"
    "var session = cluster.Connect();"
)

add_text_box(slide, Inches(0.5), Inches(1.5), Inches(5.5), Inches(0.4), "NuGet Package", 14, True, DARK_BLUE)
box1 = add_shape(slide, Inches(0.5), Inches(1.95), Inches(5.5), Inches(2.0), RGBColor(0x1E, 0x1E, 0x2E))
tf = box1.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = csharp_dep; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

add_text_box(slide, Inches(6.5), Inches(1.5), Inches(6), Inches(0.4), "Application Code", 14, True, DARK_BLUE)
box2 = add_shape(slide, Inches(6.5), Inches(1.95), Inches(6.3), Inches(3.3), RGBColor(0x1E, 0x1E, 0x2E))
tf = box2.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = csharp_usage; p.font.size = Pt(11); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

items = [
    "Implements IAuthProvider and IAuthProviderNamed from CassandraCSharpDriver",
    "Uses MSAL.NET (Microsoft.Identity.Client) for token acquisition",
    "Supports Client Credentials, Managed Identity, and Interactive flows",
    "Async-native: uses AcquireTokenForClient().ExecuteAsync()",
    "Package: Apache.Cassandra.EntraIdAuth on NuGet",
]
add_bullet_list(slide, Inches(0.5), Inches(4.5), Inches(12), Inches(2.5), items, 14, GRAY)

add_slide_number(slide, 21, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 22 — CLIENT DRIVER: PYTHON
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Client Driver — Python (cassandra-driver)", "pip package with msal integration")

py_dep = "pip install cassandra-entra-id-auth"
py_usage = (
    "# Python — Client Credentials\n"
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
    "session = cluster.connect()"
)

add_text_box(slide, Inches(0.5), Inches(1.5), Inches(4), Inches(0.4), "pip Install", 14, True, DARK_BLUE)
box1 = add_shape(slide, Inches(0.5), Inches(1.95), Inches(4), Inches(0.6), RGBColor(0x1E, 0x1E, 0x2E))
tf = box1.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = py_dep; p.font.size = Pt(12); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

add_text_box(slide, Inches(5), Inches(1.5), Inches(7.5), Inches(0.4), "Application Code", 14, True, DARK_BLUE)
box2 = add_shape(slide, Inches(5), Inches(1.95), Inches(7.8), Inches(4.3), RGBColor(0x1E, 0x1E, 0x2E))
tf = box2.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = py_usage; p.font.size = Pt(12); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

items = [
    "Implements AuthProvider from cassandra.auth module",
    "Uses msal Python library for token acquisition",
    "Supports: client_secret, managed_identity, username_password, device_code, interactive",
    "Token caching via MSAL's built-in in-memory cache",
    "Package: cassandra-entra-id-auth on PyPI",
    "Dependencies: msal>=1.20.0, cassandra-driver>=3.25.0",
]
add_bullet_list(slide, Inches(0.5), Inches(3.0), Inches(4.2), Inches(4), items, 13, GRAY)

add_slide_number(slide, 22, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 23 — CQLSH INTEGRATION
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "CQLSH — Native Entra ID Support", "Built into Cassandra's cqlsh — no extra packages needed")

cqlshrc = (
    "# ~/.cassandra/cqlshrc\n"
    "[auth_provider]\n"
    "module = cqlshlib.entra_id_auth_provider\n"
    "classname = EntraIdAuthProvider\n"
    "tenant_id = YOUR-TENANT-ID\n"
    "client_id = YOUR-CLIENT-ID\n"
    "client_secret = YOUR-SECRET"
)

cqlsh_cmd = (
    "# Run cqlsh with Entra ID auth\n"
    "cqlsh --cqlshrc=~/.cassandra/cqlshrc cassandra-host\n"
    "\n"
    "# Or use environment variables\n"
    "export ENTRA_TENANT_ID=YOUR-TENANT-ID\n"
    "export ENTRA_CLIENT_ID=YOUR-CLIENT-ID\n"
    "export ENTRA_CLIENT_SECRET=YOUR-SECRET\n"
    "cqlsh cassandra-host"
)

add_text_box(slide, Inches(0.5), Inches(1.5), Inches(6), Inches(0.4), "cqlshrc Configuration", 14, True, DARK_BLUE)
box1 = add_shape(slide, Inches(0.5), Inches(1.95), Inches(5.5), Inches(2.5), RGBColor(0x1E, 0x1E, 0x2E))
tf = box1.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = cqlshrc; p.font.size = Pt(12); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

add_text_box(slide, Inches(6.5), Inches(1.5), Inches(6), Inches(0.4), "Usage", 14, True, DARK_BLUE)
box2 = add_shape(slide, Inches(6.5), Inches(1.95), Inches(6.3), Inches(2.5), RGBColor(0x1E, 0x1E, 0x2E))
tf = box2.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = cqlsh_cmd; p.font.size = Pt(12); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

items = [
    "Ships with Cassandra — no pip install needed (module in pylib/cqlshlib/)",
    "Supports: client_secret, managed_identity, device_code, interactive",
    "Uses msal Python library (only external dependency, installed via pip install msal)",
    "LOGIN command re-authenticates with fresh token (no password prompt needed)",
    "Username extracted from JWT's preferred_username claim",
    "Prompt shows actual Entra ID identity: user@contoso.com@cqlsh>",
]
add_bullet_list(slide, Inches(0.5), Inches(4.8), Inches(12), Inches(2.5), items, 14, GRAY)

add_slide_number(slide, 23, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 24 — ALL DRIVERS SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "All Client Drivers — Comparison Matrix")

headers = ["", "Java 3.x", "Java 4.x", "C# .NET", "Python", "CQLSH"]
rows = [
    ["Package", "cassandra-entra-\nid-auth-driver3", "cassandra-entra-\nid-auth-driver4", "Apache.Cassandra.\nEntraIdAuth", "cassandra-entra-\nid-auth", "Built-in\n(cqlshlib)"],
    ["Package Manager", "Maven", "Maven", "NuGet", "pip", "N/A"],
    ["MSAL Library", "msal4j", "msal4j", "MSAL.NET", "msal (Python)", "msal (Python)"],
    ["Client Credentials", "✅", "✅", "✅", "✅", "✅"],
    ["Managed Identity", "✅", "✅", "✅", "✅", "✅"],
    ["Interactive", "✅", "✅", "✅", "✅", "✅"],
    ["Device Code", "✅", "✅", "✅", "✅", "✅"],
    ["ROPC", "✅", "✅", "✅", "✅", "N/A"],
    ["Token Caching", "MSAL built-in", "MSAL built-in", "MSAL built-in", "MSAL built-in", "MSAL built-in"],
    ["Uber JAR / Shading", "✅ (Shade)", "✅ (Shade)", "N/A", "N/A", "N/A"],
]

table_left = Inches(0.4)
table_top = Inches(1.5)
col_widths = [Inches(1.8), Inches(2.1), Inches(2.1), Inches(2.1), Inches(2.1), Inches(2.1)]
rh = Inches(0.48)

# Header
x = table_left
for j, h in enumerate(headers):
    cell = add_rect(slide, x, table_top, col_widths[j], rh, DARK_BLUE)
    set_text(cell, h, 11, True, WHITE)
    x += col_widths[j]

for i, row in enumerate(rows):
    x = table_left
    bg = LIGHT_GRAY if i % 2 == 0 else WHITE
    for j, val in enumerate(row):
        cell_bg = DARK_BLUE if j == 0 else bg
        cell_fg = WHITE if j == 0 else BLACK
        cell = add_rect(slide, x, table_top + rh * (i + 1), col_widths[j], rh, cell_bg, RGBColor(0xDD, 0xDD, 0xDD))
        set_text(cell, val, 9 if j > 0 else 10, j == 0, cell_fg)
        x += col_widths[j]

add_slide_number(slide, 24, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 25 — SASL WIRE FORMAT
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "SASL PLAIN Wire Format — How JWT Travels on the Wire")

add_text_box(slide, Inches(0.5), Inches(1.5), Inches(12), Inches(0.5),
             "All drivers send the JWT token inside a standard SASL PLAIN response. Cassandra's native protocol\n"
             "already supports SASL — no protocol changes needed. The JWT is sent in the PASSWORD field.",
             14, color=GRAY)

# Wire format diagram
add_text_box(slide, Inches(0.5), Inches(2.5), Inches(12), Inches(0.4),
             "SASL PLAIN Response (RFC 4616):", 16, True, DARK_BLUE)

# Byte layout
fields = [
    ("authzId\n(empty)", Inches(1.5), LIGHT_GRAY),
    ("NUL\n0x00", Inches(0.6), ACCENT_RED),
    ("authnId\nuser@contoso.com", Inches(2.5), LIGHT_BLUE),
    ("NUL\n0x00", Inches(0.6), ACCENT_RED),
    ("password\neyJhbGciOiJSUzI1NiIsInR5cCI6...(JWT token)", Inches(6.5), AZURE_BLUE),
]

x = Inches(0.5)
y = Inches(3.1)
for (label, width, color) in fields:
    fg = WHITE if color in (ACCENT_RED, AZURE_BLUE) else BLACK
    box = add_rect(slide, x, y, width, Inches(1.0), color, DARK_BLUE)
    set_text(box, label, 11, True, fg)
    x += width

# Explanation
items = [
    "authzId: Empty (authorization identity not used)",
    "NUL (0x00): Standard separator byte per RFC 4616",
    "authnId: The username / email — Cassandra uses this if token validation fails",
    "password: The full JWT access token (typically 1000-2000 bytes)",
    "The JWT in the password field is the PRIMARY credential — username is secondary",
    "Server extracts preferred_username from the JWT — the authnId field is advisory only",
]
add_bullet_list(slide, Inches(0.5), Inches(4.5), Inches(12), Inches(2.8), items, 14, GRAY)

add_slide_number(slide, 25, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 26 — JWKS & TOKEN VALIDATION DEEP DIVE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "JWKS & Token Validation — Deep Dive", "How the server verifies tokens without calling Entra ID per request")

# JWKS flow
add_text_box(slide, Inches(0.5), Inches(1.5), Inches(6), Inches(0.4), "JWKS Key Cache Architecture", 16, True, DARK_BLUE)

cache_box = add_shape(slide, Inches(0.5), Inches(2.0), Inches(6), Inches(1.8), LIGHT_BLUE, AZURE_BLUE)
tf = cache_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]
p.text = ("ConcurrentHashMap<kid, PublicKey>\n"
          "● TTL: 24 hours (configurable)\n"
          "● Thread-safe refresh with double-checked locking\n"
          "● Only RSA signing keys (kty=RSA, use=sig)\n"
          "● Endpoint: login.microsoftonline.com/{tenant}/discovery/v2.0/keys")
p.font.size = Pt(12); p.font.color.rgb = DARK_BLUE; p.alignment = PP_ALIGN.LEFT

# JWT structure
add_text_box(slide, Inches(7), Inches(1.5), Inches(6), Inches(0.4), "JWT Token Structure", 16, True, DARK_BLUE)

jwt_struct = (
    "Header (base64url):\n"
    '  {"alg":"RS256","kid":"nOo3ZD...","typ":"JWT"}\n\n'
    "Payload (base64url):\n"
    '  {"iss":"https://login.microsoftonline.com/{tenant}/v2.0",\n'
    '   "aud":"client-id","exp":1740000000,\n'
    '   "preferred_username":"user@contoso.com",\n'
    '   "groups":["uuid1","uuid2"],"roles":["Admin"]}\n\n'
    "Signature:\n"
    "  RS256(base64url(header) + '.' + base64url(payload))"
)
jwt_box = add_shape(slide, Inches(7), Inches(2.0), Inches(5.8), Inches(3.5), RGBColor(0x1E, 0x1E, 0x2E))
tf = jwt_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = jwt_struct; p.font.size = Pt(10); p.font.color.rgb = RGBColor(0xA6, 0xE2, 0x2E); p.alignment = PP_ALIGN.LEFT; p.font.name = "Consolas"

# Validation steps
add_text_box(slide, Inches(0.5), Inches(4.0), Inches(6), Inches(0.4), "Claim Validation Rules", 14, True, DARK_BLUE)
rules = [
    "iss ∈ { v1: https://sts.windows.net/{tenant}/,  v2: https://login.microsoftonline.com/{tenant}/v2.0 }",
    "aud == configured client_id (your app registration)",
    "exp + 300s (clock skew) > current_time  →  token not expired",
    "nbf - 300s (clock skew) < current_time  →  token is active",
    "alg == RS256 (only algorithm accepted)",
    "kid matches a key from the JWKS cache → fetch fresh if miss",
]
add_bullet_list(slide, Inches(0.5), Inches(4.5), Inches(12), Inches(2.8), rules, 13, GRAY)

add_slide_number(slide, 26, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 27 — MANAGED IDENTITY DEEP DIVE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Azure Managed Identity — Zero-Secret Authentication", "The recommended approach for Azure-hosted workloads")

# Diagram
vm_box = add_shape(slide, Inches(0.5), Inches(2), Inches(3), Inches(2), LIGHT_BLUE, AZURE_BLUE)
set_text(vm_box, "Azure VM / AKS Pod\n\nYour Application\n+ Cassandra Driver\n+ MSAL", 13, True, DARK_BLUE)

imds_box = add_shape(slide, Inches(4.5), Inches(2), Inches(3.5), Inches(2), AZURE_BLUE)
set_text(imds_box, "Azure IMDS\n\nInstance Metadata\nService\n169.254.169.254", 13, True, WHITE)

entra_box = add_shape(slide, Inches(9), Inches(2), Inches(3.5), Inches(2), DARK_BLUE)
set_text(entra_box, "Microsoft Entra ID\n\nToken Issuer\nJWKS Provider", 13, True, WHITE)

# Arrows
a1 = add_arrow(slide, Inches(3.6), Inches(2.6), Inches(0.8), Inches(0.5), AZURE_BLUE)
set_text(a1, "①", 10, True, WHITE)
a2 = add_arrow(slide, Inches(8.1), Inches(2.6), Inches(0.8), Inches(0.5), DARK_BLUE)
set_text(a2, "②", 10, True, WHITE)

add_text_box(slide, Inches(3.7), Inches(4.2), Inches(4), Inches(0.4), "③ JWT returned to app → sent to Cassandra", 12, True, GRAY)

items = [
    "System-assigned Managed Identity: Enabled on the VM/AKS, tied to that resource lifecycle",
    "User-assigned Managed Identity: Created independently, can be shared across resources",
    "MSAL handles the IMDS call internally — your code just calls acquireToken()",
    "NO client secrets, NO certificates, NO credentials to rotate",
    "Token is scoped to api://{client_id}/.default",
    "Azure automatically rotates the underlying credential",
    "Best for: production workloads running on Azure infrastructure",
]
add_bullet_list(slide, Inches(0.5), Inches(4.7), Inches(12), Inches(2.5), items, 14, GRAY)

add_slide_number(slide, 27, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 28 — SECURITY CONSIDERATIONS
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Security Considerations", "Defence in depth for production deployments")

categories = [
    ("Transport Security", [
        "Enable client-to-node TLS encryption (native_transport_port_ssl)",
        "JWT tokens are bearer tokens — must be encrypted in transit",
        "Use TLS 1.2+ with strong cipher suites",
    ], AZURE_BLUE),
    ("Token Security", [
        "Tokens are short-lived (typically 1 hour)",
        "Clock skew tolerance: 5 minutes (configurable)",
        "JWKS keys refreshed every 24 hours",
        "Only RS256 signatures accepted",
    ], ACCENT_GREEN),
    ("Configuration Security", [
        "Store client secrets in Azure Key Vault",
        "Use Managed Identity where possible (no secrets)",
        "Restrict conf/entra-id.properties file permissions",
        "Validate tenant_id format to prevent injection",
    ], ACCENT_ORANGE),
    ("Audit & Monitoring", [
        "All auth events logged via SLF4J",
        "Failed validations include reason codes",
        "Entra ID sign-in logs show all token requests",
        "Conditional Access policies enforced at token issuance",
    ], MID_BLUE),
]

for i, (title, items, color) in enumerate(categories):
    col = i % 2
    row = i // 2
    left = Inches(0.5 + col * 6.4)
    top = Inches(1.5 + row * 2.8)
    box = add_shape(slide, left, top, Inches(6), Inches(2.5), LIGHT_GRAY, color, Pt(2))
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title; p.font.size = Pt(16); p.font.bold = True; p.font.color.rgb = color; p.alignment = PP_ALIGN.LEFT
    for item in items:
        p2 = tf.add_paragraph(); p2.text = "  ● " + item; p2.font.size = Pt(12); p2.font.color.rgb = GRAY; p2.alignment = PP_ALIGN.LEFT

add_slide_number(slide, 28, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 29 — BACKWARD COMPATIBILITY
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Backward Compatibility & Migration", "Moving from PasswordAuthenticator to EntraID")

# Before / After
before_box = add_shape(slide, Inches(0.5), Inches(1.5), Inches(5.8), Inches(2.5), LIGHT_GRAY, ACCENT_RED, Pt(2))
tf = before_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "BEFORE (PasswordAuthenticator)"; p.font.size = Pt(16); p.font.bold = True; p.font.color.rgb = ACCENT_RED; p.alignment = PP_ALIGN.LEFT
for item in ["authenticator: PasswordAuthenticator", "Passwords in system_auth.roles", "Manual user provisioning", "Per-user permission grants", "No MFA, no SSO"]:
    p2 = tf.add_paragraph(); p2.text = "  ● " + item; p2.font.size = Pt(13); p2.font.color.rgb = GRAY; p2.alignment = PP_ALIGN.LEFT

after_box = add_shape(slide, Inches(7), Inches(1.5), Inches(5.8), Inches(2.5), LIGHT_BLUE, ACCENT_GREEN, Pt(2))
tf = after_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "AFTER (EntraIdAuthenticator)"; p.font.size = Pt(16); p.font.bold = True; p.font.color.rgb = ACCENT_GREEN; p.alignment = PP_ALIGN.LEFT
for item in ["authenticator: EntraIdAuthenticator", "JWT tokens from Entra ID", "Centralized identity via Azure AD", "Group-based permission mapping", "Full MFA + Conditional Access"]:
    p2 = tf.add_paragraph(); p2.text = "  ● " + item; p2.font.size = Pt(13); p2.font.color.rgb = GRAY; p2.alignment = PP_ALIGN.LEFT

# Migration steps
add_text_box(slide, Inches(0.5), Inches(4.3), Inches(12), Inches(0.4),
             "Rolling Migration Steps:", 16, True, DARK_BLUE)
migration = [
    "1. Deploy plugin JAR to all nodes (copy to lib/) — no restart needed yet",
    "2. Create Cassandra roles matching Entra ID principal names (preferred_username)",
    "3. Set up entra_group_roles mappings for group-based authorization",
    "4. Update cassandra.yaml: authenticator → EntraIdAuthenticator, authorizer → EntraIdAuthorizer",
    "5. Rolling restart — one node at a time, verify each node's auth before proceeding",
    "6. Update client applications to use MSAL-based auth providers",
    "7. (Optional) Disable legacy passwords once all clients are migrated",
]
add_bullet_list(slide, Inches(0.5), Inches(4.8), Inches(12), Inches(2.5), migration, 13, GRAY)

add_slide_number(slide, 29, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 30 — TESTING STRATEGY
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Testing Strategy", "Unit tests, integration tests, and manual verification")

test_categories = [
    ("Unit Tests (18 passing)", [
        "Locally generated RSA key pair",
        "Signed JWTs without network calls",
        "Valid token decoding & claim extraction",
        "Expired, tampered, wrong-audience tokens",
        "Wrong signing key / algorithm rejection",
        "Principal name priority (5 fallback levels)",
        "Claims cache hit / miss",
        "System property + properties file config",
    ], ACCENT_GREEN),
    ("Integration Tests", [
        "Real Entra ID tenant + app registration",
        "Client credentials flow end-to-end",
        "Managed Identity on Azure VM",
        "Group claims → role permission resolution",
        "Token expiry & automatic refresh",
        "Multi-node cluster with rolling restart",
        "Mixed auth (Entra + Password users)",
    ], AZURE_BLUE),
    ("Manual Verification", [
        "CQLSH interactive login",
        "LOGIN command token refresh",
        "Azure Portal audit log verification",
        "Conditional Access policy enforcement",
        "Error message clarity for misconfig",
    ], ACCENT_ORANGE),
]

for i, (title, items, color) in enumerate(test_categories):
    left = Inches(0.4 + i * 4.3)
    hdr = add_shape(slide, left, Inches(1.5), Inches(3.9), Inches(0.6), color)
    set_text(hdr, title, 13, True, WHITE)
    body = add_shape(slide, left, Inches(2.1), Inches(3.9), Inches(4.8), LIGHT_GRAY, color)
    tf = body.text_frame; tf.word_wrap = True
    for j, item in enumerate(items):
        if j == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = "  ● " + item; p.font.size = Pt(12); p.font.color.rgb = GRAY; p.alignment = PP_ALIGN.LEFT
        p.space_before = Pt(3)

add_slide_number(slide, 30, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 31 — DEPLOYMENT ARCHITECTURE
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, WHITE)
add_top_bar(slide, "Production Deployment Architecture", "Complete component diagram for service providers")

# Cloud / Entra ID
entra_cloud = add_shape(slide, Inches(3.5), Inches(1.5), Inches(6), Inches(1.3), AZURE_BLUE)
set_text(entra_cloud, "☁️  Microsoft Entra ID  (login.microsoftonline.com)\nToken Issuance  |  JWKS Endpoint  |  Conditional Access  |  Audit Logs", 13, True, WHITE)

# Client tier
client_box = add_shape(slide, Inches(0.3), Inches(3.5), Inches(4), Inches(3.2), LIGHT_BLUE, AZURE_BLUE)
tf = client_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "Application Tier"; p.font.size = Pt(14); p.font.bold = True; p.font.color.rgb = DARK_BLUE; p.alignment = PP_ALIGN.CENTER
for line in ["\n● Java / C# / Python apps", "● CQLSH admin tools", "● MSAL for token acquisition", "● Pre-built auth provider plugins", "● Token cached & auto-refreshed"]:
    p2 = tf.add_paragraph(); p2.text = line; p2.font.size = Pt(11); p2.font.color.rgb = DARK_BLUE; p2.alignment = PP_ALIGN.LEFT

# Cassandra tier
cass_box = add_shape(slide, Inches(5.2), Inches(3.5), Inches(4), Inches(3.2), CASSANDRA_TEAL)
tf = cass_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "Cassandra Cluster"; p.font.size = Pt(14); p.font.bold = True; p.font.color.rgb = WHITE; p.alignment = PP_ALIGN.CENTER
for line in ["\n● Plugin JAR in lib/", "● EntraIdAuthenticator", "● EntraIdTokenValidator", "● EntraIdAuthorizer", "● entra_group_roles table"]:
    p2 = tf.add_paragraph(); p2.text = line; p2.font.size = Pt(11); p2.font.color.rgb = WHITE; p2.alignment = PP_ALIGN.LEFT

# Azure infra
azure_box = add_shape(slide, Inches(10), Inches(3.5), Inches(2.8), Inches(3.2), DARK_BLUE)
tf = azure_box.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; p.text = "Azure Platform"; p.font.size = Pt(14); p.font.bold = True; p.font.color.rgb = WHITE; p.alignment = PP_ALIGN.CENTER
for line in ["\n● Key Vault", "  (secrets)", "● Managed Identity", "  (auto tokens)", "● RBAC", "  (access control)"]:
    p2 = tf.add_paragraph(); p2.text = line; p2.font.size = Pt(11); p2.font.color.rgb = WHITE; p2.alignment = PP_ALIGN.LEFT

# Arrows
add_arrow(slide, Inches(4.5), Inches(4.8), Inches(0.5), Inches(0.4), MID_BLUE)
add_text_box(slide, Inches(4.4), Inches(5.3), Inches(1), Inches(0.3), "TLS", 10, True, MID_BLUE, PP_ALIGN.CENTER)

add_slide_number(slide, 31, TOTAL_SLIDES)
add_footer(slide)

# ══════════════════════════════════════════════════════════════════
# SLIDE 32 — SUMMARY & NEXT STEPS
# ══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_background(slide, DARK_BLUE)

add_text_box(slide, Inches(1), Inches(0.8), Inches(11), Inches(0.8),
             "Summary & Next Steps", 36, bold=True, color=WHITE)
add_rect(slide, Inches(1), Inches(1.6), Inches(3), Inches(0.05), AZURE_BLUE)

summary_items = [
    "✅  Enterprise-grade Entra ID authentication for Apache Cassandra",
    "✅  Zero server-side external dependencies (JDK crypto + Jackson)",
    "✅  Drop-in plugin JAR — no Cassandra source modification needed",
    "✅  Group-based authorization via entra_group_roles mapping table",
    "✅  Pre-built driver plugins for Java 3.x, Java 4.x, C# .NET, Python, CQLSH",
    "✅  MSAL-powered client-side token acquisition with caching & refresh",
    "✅  Supports Client Credentials, Managed Identity, Interactive, Device Code flows",
    "✅  18 unit tests passing, comprehensive documentation",
]

y = Inches(2.0)
for item in summary_items:
    add_text_box(slide, Inches(1), y, Inches(11), Inches(0.35), item, 16, color=WHITE)
    y += Inches(0.45)

add_text_box(slide, Inches(1), Inches(5.8), Inches(11), Inches(0.5),
             "Next Steps:", 20, bold=True, color=AZURE_BLUE)

next_steps = [
    "1. Complete integration testing with a real Entra ID tenant",
    "2. Performance benchmarking (token validation latency)",
    "3. Publish plugin JARs & driver packages to Maven Central / NuGet / PyPI",
    "4. Submit for Apache Cassandra community review",
]
y = Inches(6.35)
for item in next_steps:
    add_text_box(slide, Inches(1), y, Inches(11), Inches(0.3), item, 14, color=LIGHT_BLUE)
    y += Inches(0.3)

add_slide_number(slide, 32, TOTAL_SLIDES)

# ── Save ──────────────────────────────────────────────────────────
output_dir = os.path.dirname(os.path.abspath(__file__))
pptx_path = os.path.join(output_dir, "Cassandra_EntraID_Auth.pptx")
prs.save(pptx_path)
print(f"✅ PowerPoint saved: {pptx_path}")
print(f"   Slides: {TOTAL_SLIDES}")
print(f"   Size: {os.path.getsize(pptx_path) / 1024:.1f} KB")


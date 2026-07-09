"""Data models for the research pipeline."""

import re
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class AuthMethod(str, Enum):
    OAUTH2 = "OAuth2"
    API_KEY = "API Key"
    BASIC = "Basic Auth"
    BEARER_TOKEN = "Bearer Token"
    JWT = "JWT"
    HMAC = "HMAC"
    CUSTOM = "Custom/Proprietary"
    NONE = "No Auth / Open"

class AccessLevel(str, Enum):
    SELF_SERVE_FREE = "Self-serve (Free)"
    SELF_SERVE_TRIAL = "Self-serve (Free Trial)"
    SELF_SERVE_PAID = "Self-serve (Paid Plan Required)"
    ADMIN_APPROVAL = "Admin/Org Approval Required"
    PARTNER_GATED = "Partner/Contact-Sales Gated"
    OPEN_SOURCE = "Open Source / Self-hosted"
    UNKNOWN = "Unknown / Unclear"

class APIType(str, Enum):
    REST = "REST"
    GRAPHQL = "GraphQL"
    REST_AND_GRAPHQL = "REST + GraphQL"
    WEBSOCKET = "WebSocket"
    GRPC = "gRPC"
    SDK_ONLY = "SDK Only (No REST)"
    NONE = "No Public API"

class APIBreadth(str, Enum):
    BROAD = "Broad (50+ endpoints)"
    MODERATE = "Moderate (10-50 endpoints)"
    NARROW = "Narrow (<10 endpoints)"
    UNDOCUMENTED = "Undocumented / Unknown"

class Buildability(str, Enum):
    READY = "Ready"
    FEASIBLE = "Feasible"
    BLOCKED = "Blocked"
    GATED = "Gated"

class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class AppResearchResult(BaseModel):
    """Structured research result for a single app."""
    app_name: str = Field(description="Name of the app")
    category: str = Field(description="Category (e.g., 'CRM and Sales')")
    one_liner: str = Field(description="One-line description of what the app does")
    
    auth_methods: list[AuthMethod] = Field(description="All auth methods supported by the API")
    primary_auth: AuthMethod = Field(description="The primary/recommended auth method")
    
    access_level: AccessLevel = Field(description="Whether a developer can self-serve or if access is gated")
    access_detail: str = Field(description="Specific detail about access: e.g., 'Free tier with 100 req/day'")
    
    api_type: APIType = Field(description="Type of public API available")
    api_breadth: APIBreadth = Field(description="How broad the API surface is")
    has_graphql: bool = Field(description="Whether GraphQL API is available")
    api_doc_quality: str = Field(description="Brief assessment: 'Excellent', 'Good', 'Fair', 'Poor', 'None'")
    
    existing_mcp: bool = Field(description="Whether an MCP server already exists")
    mcp_detail: Optional[str] = Field(default=None, description="Details about existing MCP server")
    
    buildability: Buildability = Field(description="Could this be an agent toolkit today?")
    main_blocker: Optional[str] = Field(default=None, description="Primary blocker if not 'Ready'")
    
    evidence_urls: list[str] = Field(description="URLs of docs/articles used as evidence")
    confidence: Confidence = Field(description="Confidence level in findings")
    notes: Optional[str] = Field(default=None, description="Additional notes or caveats")

class AppInput(BaseModel):
    """Input representation of an app from apps.md."""
    app_name: str
    website_hint: str
    category: str
    app_number: int

class VerificationResult(BaseModel):
    """Result of verifying a specific claim."""
    app_name: str
    field_name: str
    agent_value: str
    actual_value: str
    is_correct: bool
    evidence_url: str
    notes: str
    agent_trajectory: list[str] = Field(default_factory=list, description="The steps the agent took to verify")

class AnalysisResult(BaseModel):
    """Results from pattern analysis."""
    auth_distribution: dict[str, int]
    access_by_category: dict[str, dict[str, int]]
    buildability_breakdown: dict[str, int]
    top_patterns: list[str]
    easy_wins: list[str]
    hard_nuts: list[str]
    executive_summary: str

def parse_apps_md(filepath: str) -> list[AppInput]:
    """Parse apps.md to extract the list of apps to research."""
    apps = []
    current_category = "Unknown"
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    lines = content.split('\n')
    app_counter = 1
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for category header
        if line.startswith('## '):
            current_category = line[3:].strip()
            continue
            
        # Check for app entry (e.g., "| 1 | Salesforce | salesforce.com |")
        match = re.match(r'\|\s*\d+\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|', line)
        if match and not match.group(1).strip() == "App":
            app_name = match.group(1).strip()
            website_hint = match.group(2).strip()
            
            apps.append(AppInput(
                app_name=app_name,
                website_hint=website_hint,
                category=current_category,
                app_number=app_counter
            ))
            app_counter += 1
            
    return apps

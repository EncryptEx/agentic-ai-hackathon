"""Risk scoring, alert, and decision explainability models."""

from enum import Enum
from typing import List, Dict, Any, Optional
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def model_dump(self):
            return self.__dict__
        def dict(self):
            return self.__dict__
    def Field(default=None, **kwargs):
        return default

class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AMLAlert(BaseModel):
    alert_id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    score_impact: float
    summary: str
    trigger_details: Dict[str, Any]
    supporting_transaction_ids: List[str] = Field(default_factory=list)

class FraudAlert(BaseModel):
    alert_id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    score_impact: float
    summary: str
    trigger_details: Dict[str, Any]
    supporting_transaction_ids: List[str] = Field(default_factory=list)

class PillarScore(BaseModel):
    pillar_name: str
    weight: float
    raw_score: float = Field(..., ge=0.0, le=100.0, description="Raw 0-100 pillar score")
    weighted_score: float = Field(..., description="raw_score * weight")
    contributing_factors: List[str] = Field(default_factory=list)

class CustomerRiskAssessment(BaseModel):
    customer_id: str
    assessment_timestamp: str
    composite_score: float = Field(..., ge=0.0, le=100.0)
    risk_tier: RiskTier
    
    # Pillar breakdowns
    kyc_pillar: PillarScore
    purpose_pillar: PillarScore
    product_pillar: PillarScore
    behavioral_pillar: PillarScore # AML Transaction Monitoring
    fraud_pillar: PillarScore      # Fraud Risk & Digital Footprint
    
    # Transaction Monitoring AML Alerts
    alerts: List[AMLAlert] = Field(default_factory=list)
    alert_count: int = 0
    highest_alert_severity: Optional[AlertSeverity] = None

    # Fraud Alerts
    fraud_alerts: List[FraudAlert] = Field(default_factory=list)
    fraud_alert_count: int = 0
    highest_fraud_severity: Optional[AlertSeverity] = None

    # Sub-scores
    aml_score: float = 0.0
    fraud_score: float = 0.0
    
    # Governance & Action recommendations
    recommended_action: str
    action_checklist: List[str] = Field(default_factory=list)
    executive_summary: str

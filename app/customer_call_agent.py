"""Customer Outreach & Verification Agent with Strict Anti-Tipping-Off Safeguards.

Under international financial crime laws (e.g., UK Proceeds of Crime Act 2002 § 333A,
US Bank Secrecy Act 31 U.S.C. § 5318(g)(2), EU AML Directives, FATF Recommendation 21),
financial institutions are strictly prohibited from tipping off a customer that an
AML/Fraud investigation is taking place, that a Suspicious Activity Report (SAR) has
been considered, or that internal risk flags have been triggered.

This agent operates as a realistic, professional, and courteous Customer Verification
Officer (Agent Claire Sterling, Valiant Bank Client Care & Verification). It conducts
targeted customer inquiries (clarifying source of funds, purpose of international wires,
substantiating cash deposits, verifying digital identity) while strictly adhering to
anti-tipping-off statutory guardrails.

ALL DATA IS SYNTHETIC AND FICTIONAL.
"""

from __future__ import annotations

import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_BASE_DIR, ".env")
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)
load_dotenv()

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.tools import (
    get_customer_profile,
    get_kyc_dossier,
    get_transactions,
    get_transaction_alerts,
    get_fraud_alerts,
    get_risk_assessment,
)
from storage.database import DatabaseManager

MODEL = "gemini-3.8-flash"

# Statutory prohibited terms under Anti-Tipping-Off rules
PROHIBITED_TIPPING_OFF_TERMS = [
    "sar",
    "suspicious activity report",
    "str",
    "money laundering",
    "money mule",
    "structuring",
    "smurfing",
    "aml alert",
    "fraud alert",
    "tm-01",
    "tm-02",
    "tm-03",
    "tm-04",
    "tm-05",
    "fr-01",
    "fr-02",
    "fr-03",
    "fr-04",
    "fr-05",
    "tip off",
    "tipping off",
    "law enforcement referral",
    "fincen",
    "police report",
    "internal risk score",
    "critical risk",
    "under investigation",
    "criminal",
]


class CallTurnResponse(BaseModel):
    agent_message: str = Field(..., description="The spoken response from Agent Claire Sterling to the customer.")
    customer_sentiment: str = Field(..., description="Detected customer demeanor: COOPERATIVE, NERVOUS, DEFENSIVE, AGITATED, or CONFUSED.")
    agent_emotion: str = Field(default="warm_reassuring", description="Vocal emotional delivery tone: warm_reassuring, gentle_calming, compassionate_probing, polite_documentation, or soothing_empathy.")
    plausibility_score: float = Field(..., description="Current plausibility score of customer's statements from 0.0 to 100.0.")
    plausibility_verdict: str = Field(..., description="PLAUSIBLE_SUPPORTED, REQUIRES_DOCUMENTATION, EVASIVE_UNSUBSTANTIATED, or HIGH_RISK_CONTRADICTORY.")
    extracted_facts: List[str] = Field(default_factory=list, description="Key factual claims made by the customer during this turn.")
    evasive_flags: List[str] = Field(default_factory=list, description="Any detected evasiveness, deflection, or contradictions against bank ledger.")
    inquiry_complete: bool = Field(default=False, description="True if all critical verification questions have been asked and answered.")


class CustomerCallSession:
    """Manages an interactive voice/video verification call with a customer."""

    def __init__(self, customer_id: str, alert_id: Optional[str] = None):
        self.session_id = f"CALL-{uuid.uuid4().hex[:10].upper()}"
        self.customer_id = customer_id
        self.alert_id = alert_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.turns: List[Dict[str, Any]] = []
        self.history: List[Dict[str, str]] = []
        self.extracted_claims: List[str] = []
        self.detected_flags: List[str] = []
        self.current_plausibility: float = 75.0
        self.current_verdict: str = "IN_PROGRESS"
        
        # Load customer case context
        self.kyc = get_kyc_dossier(customer_id)
        self.profile = get_customer_profile(customer_id)
        tx_data = get_transactions(customer_id)
        self.transactions = tx_data if isinstance(tx_data, list) else tx_data.get("transactions", [])
        self.tm_alerts = get_transaction_alerts(customer_id)
        self.fraud_alerts = get_fraud_alerts(customer_id)
        self.assessment = get_risk_assessment(customer_id)
        
        self.customer_name = self.kyc.get("name") or f"{self.profile.get('first_name', '')} {self.profile.get('last_name', '')}".strip() or "Valued Customer"
        self._init_inquiry_goals()

    def _init_inquiry_goals(self):
        """Identifies specific factual items that need verification without tipping off."""
        self.inquiry_goals = []
        
        # Check cash structuring (TM-01)
        has_structuring = any(a.get("rule_id") == "TM-01" for a in self.tm_alerts)
        if has_structuring:
            self.inquiry_goals.append("Confirm the origin and underlying commercial or personal nature of recent cash deposits.")
            self.inquiry_goals.append("Ask if standard commercial documentation (sales receipts, contracts, invoices) exists for cash proceeds.")

        # Check money mule / pass-through (TM-02)
        has_mule = any(a.get("rule_id") == "TM-02" for a in self.tm_alerts)
        if has_mule:
            self.inquiry_goals.append("Clarify the nature of the relationship with the overseas wire sender and reason for rapid outbound transfer.")
            self.inquiry_goals.append("Verify whether the customer acted on instructions from a third party or employment offer.")

        # Check high turnover (TM-03) or outlier single transfer (TM-04)
        has_turnover = any(a.get("rule_id") in ("TM-03", "TM-04") for a in self.tm_alerts)
        if has_turnover and not has_structuring and not has_mule:
            self.inquiry_goals.append("Verify significant change in account volume compared to initial account opening baseline.")

        # Check fraud / ATO / device anomalies
        has_fraud = len(self.fraud_alerts) > 0
        if has_fraud:
            self.inquiry_goals.append("Confirm whether the customer personally initiated recent digital banking sessions and recognized login devices.")

        if not self.inquiry_goals:
            self.inquiry_goals.append("Conduct periodic profile verification and confirm recent transactions on the account.")

    def _get_client(self) -> genai.Client:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            return genai.Client(api_key=api_key)
        return genai.Client()

    def synthesize_speech(
        self,
        text: str,
        emotion: str = "warm_reassuring",
        voice_name: str = "Aoede",
    ) -> Optional[str]:
        """Synthesizes natural Google Gemini neural speech with authentic human emotion, cadence, and warmth."""
        try:
            client = self._get_client()
            emotion_prompts = {
                "warm_reassuring": "Speaking with authentic warmth, gentle smile in the voice, natural breath pauses, and professional friendliness",
                "gentle_calming": "Speaking softly with deep empathy, soothing reassurance, comforting cadence, and calm patience to alleviate anxiety",
                "compassionate_probing": "Speaking with sincere curiosity, compassionate interest, attentive conversational inflection, and open-minded care",
                "polite_documentation": "Speaking with courteous professional clarity, encouraging tone, helpful attitude, and clear enunciation",
                "soothing_empathy": "Speaking with comforting warmth, reassuring tone, and validating friendliness",
            }
            guidance = emotion_prompts.get(emotion, emotion_prompts["warm_reassuring"])
            prompt = f"[{guidance}]: {text}"

            config = types.GenerateContentConfig(
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                )
            )

            resp = client.models.generate_content(
                model="gemini-3.8-flash-tts",
                contents=prompt,
                config=config,
            )

            for part in resp.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    return base64.b64encode(part.inline_data.data).decode("utf-8")
            return None
        except Exception as e:
            print(f"Warning: Gemini Neural TTS error: {e}")
            return None

    def generate_opening_greeting(self, voice_name: str = "Aoede") -> Dict[str, Any]:
        """Generates the opening verbal outreach greeting from Agent Claire Sterling."""
        first_name = self.profile.get("first_name") or self.customer_name.split()[0]
        greeting = (
            f"Hello {first_name}, this is Agent Claire Sterling calling from Valiant Bank's "
            f"Account Security and Client Verification Team. I hope you're having a good day. "
            f"I'm reaching out for a brief, routine security check to verify recent activity on your "
            f"account and ensure your banking records remain up to date. Do you have a couple of moments to confirm a few details with me?"
        )
        audio_b64 = self.synthesize_speech(greeting, emotion="warm_reassuring", voice_name=voice_name)
        turn_data = {
            "speaker": "agent",
            "text": greeting,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sentiment": "PROFESSIONAL",
            "plausibility": 75.0,
            "emotion": "warm_reassuring",
        }
        self.turns.append(turn_data)
        self.history.append({"role": "agent", "content": greeting})
        return {
            "session_id": self.session_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "agent_name": "Agent Claire Sterling",
            "agent_title": "Senior Customer Verification & Account Security Specialist",
            "message": greeting,
            "viseme_cues": self._estimate_visemes(greeting),
            "inquiry_goals": self.inquiry_goals,
            "plausibility": self.current_plausibility,
            "verdict": self.current_verdict,
            "audio_base64": audio_b64,
            "audio_mime": "audio/wav" if audio_b64 else None,
            "audio_emotion": "warm_reassuring",
            "voice_name": voice_name,
        }

    def process_turn(
        self,
        customer_message: str,
        voice_name: str = "Aoede",
        interrupted: bool = False,
    ) -> Dict[str, Any]:
        """Processes a conversational turn with the customer using Gemini under anti-tipping-off rules."""
        self.history.append({"role": "customer", "content": customer_message})
        self.turns.append({
            "speaker": "customer",
            "text": customer_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interrupted": interrupted,
        })

        interruption_directive = ""
        if interrupted:
            interruption_directive = (
                "\nSPECIAL NOTE ON INTERRUPTION:\n"
                "The customer just interrupted you mid-sentence while you were speaking. "
                "Do NOT be defensive or annoyed. In accordance with professional financial crime interviewing standards, "
                "gracefully and warmly yield (e.g., 'Yes, go right ahead Kimberly...', 'I understand, please go on...', "
                "'Of course, take your time...'), soothe any anxiety, and directly address their statement."
            )

        # Build prompt for Gemini dialogue turn
        system_instruction = f"""You are Agent Claire Sterling, Senior Verification & Fraud Prevention Specialist at Valiant Bank.
You are on an active, official video/phone verification call with customer {self.customer_name} (ID: {self.customer_id}).

Customer Profile:
- Occupation: {self.profile.get('occupation')} ({self.profile.get('industry', 'N/A')})
- Employer: {self.profile.get('employer_name', 'N/A')}
- Declared Monthly Turnover: ${self.profile.get('declared_expected_monthly_turnover_usd', 0.0):,.2f}
- Declared Purpose: {self.profile.get('declared_purpose_nature')}
- Stated Source of Funds: {self.profile.get('source_of_funds')}

Verification Objectives to Cover (DO NOT READ VERBATIM):
{json.dumps(self.inquiry_goals, indent=2)}

CRITICAL ANTI-TIPPING-OFF LEGAL MANDATE:
Under statutory banking regulations (POCA 2002 / BSA 31 U.S.C. / FATF Rec. 21):
1. You must NEVER inform or imply to the customer that they are suspected of money laundering, structuring, or fraud.
2. NEVER mention SAR, STR, internal risk rating, AML alert codes (TM-01, TM-02, FR-01), or law enforcement.
3. If the customer asks why you are calling or if they are in trouble, reassure them:
   "No need to worry at all — Valiant Bank regularly conducts standard transaction confirmations to protect customer accounts from unauthorized activity and ensure records are accurate."
4. If customer claims the funds are for a legitimate business (e.g. used car sales, consulting, family assistance), politely ask for standard documentation (sales contracts, invoices, proof of transaction).
5. If customer is evasive or gives illogical reasons, remain completely courteous and calm. Probe gently for names, relationships, or documentation.
6. Keep each verbal response CONCISE (2 to 4 spoken sentences) so it sounds like natural, high-trust phone dialogue.
7. Select an appropriate agent_emotion for your vocal delivery (one of: warm_reassuring, gentle_calming, compassionate_probing, polite_documentation, soothing_empathy) to reflect natural human empathy towards the customer.
{interruption_directive}

Analyze the customer's response, evaluate plausibility against the bank's records, and formulate your next spoken response.
Respond strictly in JSON matching the schema provided.
"""

        conversation_str = ""
        for h in self.history[-8:]:
            speaker = "Customer" if h["role"] == "customer" else "Agent Claire Sterling"
            conversation_str += f"{speaker}: {h['content']}\n"

        prompt = f"""Conversation history:
{conversation_str}

Evaluate the customer's latest reply: "{customer_message}"
Provide your next spoken response, sentiment, plausibility score, extracted facts, and any evasive flags.
"""

        client = self._get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=CallTurnResponse,
            ),
        )

        parsed: Optional[CallTurnResponse] = response.parsed
        if not parsed:
            # Fallback response
            agent_msg = "Thank you for sharing that information. Could you also confirm if you have supporting invoices or receipts for those transactions?"
            sentiment = "COOPERATIVE"
            plausibility = self.current_plausibility
            verdict = self.current_verdict
            extracted = []
            flags = []
            is_complete = False
            emotion = "warm_reassuring"
        else:
            # Anti-tipping-off safety filter check on agent response
            agent_msg = self._sanitize_tipping_off(parsed.agent_message)
            sentiment = parsed.customer_sentiment
            plausibility = parsed.plausibility_score
            verdict = parsed.plausibility_verdict
            extracted = parsed.extracted_facts
            flags = parsed.evasive_flags
            is_complete = parsed.inquiry_complete
            
            raw_emotion = getattr(parsed, "agent_emotion", "")
            valid_emotions = ("warm_reassuring", "gentle_calming", "compassionate_probing", "polite_documentation", "soothing_empathy")
            if raw_emotion in valid_emotions:
                emotion = raw_emotion
            elif sentiment in ("NERVOUS", "DEFENSIVE", "AGITATED"):
                emotion = "gentle_calming"
            elif verdict in ("HIGH_RISK_CONTRADICTORY", "EVASIVE_UNSUBSTANTIATED"):
                emotion = "compassionate_probing"
            elif verdict == "REQUIRES_DOCUMENTATION":
                emotion = "polite_documentation"
            else:
                emotion = "warm_reassuring"

        self.current_plausibility = plausibility
        self.current_verdict = verdict
        self.extracted_claims.extend(extracted)
        self.detected_flags.extend(flags)

        # Synthesize real neural audio with dynamic emotion
        audio_b64 = self.synthesize_speech(agent_msg, emotion=emotion, voice_name=voice_name)

        turn_record = {
            "speaker": "agent",
            "text": agent_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sentiment": sentiment,
            "emotion": emotion,
            "plausibility": plausibility,
            "extracted_facts": extracted,
            "evasive_flags": flags,
        }
        self.turns.append(turn_record)
        self.history.append({"role": "agent", "content": agent_msg})

        return {
            "session_id": self.session_id,
            "agent_message": agent_msg,
            "viseme_cues": self._estimate_visemes(agent_msg),
            "customer_sentiment": sentiment,
            "agent_emotion": emotion,
            "plausibility_score": plausibility,
            "plausibility_verdict": verdict,
            "extracted_facts": list(set(self.extracted_claims)),
            "evasive_flags": list(set(self.detected_flags)),
            "inquiry_complete": is_complete,
            "audio_base64": audio_b64,
            "audio_mime": "audio/wav" if audio_b64 else None,
            "voice_name": voice_name,
            "interrupted": interrupted,
        }

    def process_audio_turn(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        voice_name: str = "Aoede",
        interrupted: bool = False,
    ) -> Dict[str, Any]:
        """Transcribes incoming audio from customer microphone and processes the conversational turn."""
        client = self._get_client()
        transcribe_prompt = (
            "Transcribe the customer statement in this audio clip verbatim. "
            "If the audio contains no audible speech, background noise only, or is completely silent, "
            "respond strictly with EMPTY_AUDIO. Output only the transcript without extra quotes or formatting."
        )
        transcript = ""
        try:
            trans_resp = client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    transcribe_prompt,
                ],
            )
            transcript = (trans_resp.text or "").strip()
        except Exception as e:
            print(f"Warning: Audio transcription error: {e}")
            transcript = ""

        if not transcript or "EMPTY_AUDIO" in transcript:
            msg = "I'm sorry Kimberly, I couldn't quite hear that clearly over the line. Could you repeat what you just said?"
            audio_b64 = self.synthesize_speech(msg, emotion="gentle_calming", voice_name=voice_name)
            return {
                "session_id": self.session_id,
                "agent_message": msg,
                "viseme_cues": self._estimate_visemes(msg),
                "customer_sentiment": "COOPERATIVE",
                "agent_emotion": "gentle_calming",
                "plausibility_score": self.current_plausibility,
                "plausibility_verdict": self.current_verdict,
                "extracted_facts": list(set(self.extracted_claims)),
                "evasive_flags": list(set(self.detected_flags)),
                "inquiry_complete": False,
                "audio_base64": audio_b64,
                "audio_mime": "audio/wav" if audio_b64 else None,
                "voice_name": voice_name,
                "customer_transcript": "",
                "interrupted": interrupted,
            }

        result = self.process_turn(transcript, voice_name=voice_name, interrupted=interrupted)
        result["customer_transcript"] = transcript
        result["interrupted"] = interrupted
        return result

    def complete_call(self) -> Dict[str, Any]:
        """Finalizes the call, synthesizes the Customer Interview Dossier, and logs to the audit database."""
        client = self._get_client()

        transcript_text = "\n".join(
            f"[{t.get('speaker', '').upper()}]: {t.get('text', '')}"
            for t in self.turns
        )

        analysis_prompt = f"""You are the Lead Financial Crime Investigator reviewing a completed customer outreach interview.
Subject: {self.customer_name} ({self.customer_id})
Archetype: {self.profile.get('archetype')}
Declared Monthly Turnover: ${self.profile.get('declared_expected_monthly_turnover_usd', 0.0):,.2f}

Call Transcript:
{transcript_text}

Generate a formal 6-part Customer Interview & Verification Dossier:
1. Executive Summary of Customer Outreach (call duration, demeanor, willingness to cooperate)
2. Customer Stated Explanation & Source of Funds (how customer justified the transaction activity)
3. Factual Consistency & Discrepancies vs Bank Ledger (compare customer story to actual transactions, cash deposits, or wires)
4. Plausibility Assessment (Score 0-100, and category: PLAUSIBLE_SUPPORTED, INSUFFICIENT_DOCUMENTATION, EVASIVE_CONTRADICTORY, or HIGH_RISK_MULE_CONFIRMED)
5. Action Items & Documentation Required (e.g. 3 months sales invoices, proof of vehicle registration, employment verification)
6. Final Recommendation to Compliance Officer (whether to clear alert, request EDD, or proceed with SAR filing and account restriction)

Conclude with explicit synthetic data disclaimer and human compliance officer decision notice.
"""

        analysis_resp = client.models.generate_content(
            model=MODEL,
            contents=analysis_prompt,
            config=types.GenerateContentConfig(temperature=0.1),
        )
        dossier_text = analysis_resp.text or "Customer interview completed. Transcript logged."

        # Log into SQLite immutable audit ledger
        db = DatabaseManager()
        inv_id = db.log_investigation({
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "trigger_alert_id": self.alert_id,
            "trigger_rule": "Customer Outreach & Audio/Video Verification Interview",
            "risk_tier": self.assessment.get("risk_tier", "MEDIUM") if self.assessment else "MEDIUM",
            "composite_score": self.current_plausibility,
            "model_version": f"{MODEL} (Gemini Audio & Persona)",
            "raw_prompt": f"Customer Call Transcript ({len(self.turns)} turns)",
            "final_report_text": dossier_text,
            "officer_sign_off_status": "PENDING",
            "officer_name": "Agent Claire Sterling (AI Verification Specialist)",
            "officer_notes": f"Plausibility Score: {self.current_plausibility:.1f}%. Verdict: {self.current_verdict}. Customer Demeanor: {self.turns[-1].get('sentiment', 'COOPERATIVE') if self.turns else 'N/A'}.",
        })

        audit_record = db.get_investigation_audit_log(inv_id)
        sha = audit_record.get("final_report_sha256") if audit_record else ""

        return {
            "session_id": self.session_id,
            "investigation_id": inv_id,
            "sha256_digest": sha,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "turns_count": len(self.turns),
            "final_plausibility_score": self.current_plausibility,
            "final_verdict": self.current_verdict,
            "transcript": self.turns,
            "extracted_claims": list(set(self.extracted_claims)),
            "detected_flags": list(set(self.detected_flags)),
            "interview_dossier": dossier_text,
        }

    def _sanitize_tipping_off(self, text: str) -> str:
        """Safety scrub to guarantee no statutory prohibited terms slip through."""
        scrubbed = text
        for term in PROHIBITED_TIPPING_OFF_TERMS:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            if pattern.search(scrubbed):
                scrubbed = pattern.sub("routine banking verification", scrubbed)
        return scrubbed

    def _estimate_visemes(self, text: str) -> List[Dict[str, Any]]:
        """Generates real-time viseme cues for animated mouth lip-syncing."""
        words = text.split()
        cues = []
        current_time = 0.0
        for w in words:
            clean = re.sub(r'[^a-zA-Z]', '', w).lower()
            word_duration = max(0.18, len(clean) * 0.065)
            # Map simple phonemes to viseme shapes
            if any(ch in clean for ch in "ao"):
                shape = "open_o"
            elif any(ch in clean for ch in "eei"):
                shape = "wide_e"
            elif any(ch in clean for ch in "bmp"):
                shape = "closed_m"
            elif any(ch in clean for ch in "fv"):
                shape = "bottom_f"
            else:
                shape = "neutral_a"
            cues.append({
                "time": round(current_time, 2),
                "duration": round(word_duration, 2),
                "word": w,
                "viseme": shape,
            })
            current_time += word_duration + 0.04
        return cues


# Active in-memory call sessions
ACTIVE_CALL_SESSIONS: Dict[str, CustomerCallSession] = {}


def start_customer_call(customer_id: str, alert_id: Optional[str] = None, voice_name: str = "Aoede") -> Dict[str, Any]:
    """Factory function to initialize and start a new customer verification call."""
    session = CustomerCallSession(customer_id=customer_id, alert_id=alert_id)
    ACTIVE_CALL_SESSIONS[session.session_id] = session
    return session.generate_opening_greeting(voice_name=voice_name)


def process_call_turn(
    session_id: str,
    customer_message: str,
    voice_name: str = "Aoede",
    interrupted: bool = False,
) -> Dict[str, Any]:
    """Processes a response turn from the customer in an active call."""
    session = ACTIVE_CALL_SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"Call session '{session_id}' not found or expired.")
    return session.process_turn(customer_message, voice_name=voice_name, interrupted=interrupted)


def process_audio_turn(
    session_id: str,
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    voice_name: str = "Aoede",
    interrupted: bool = False,
) -> Dict[str, Any]:
    """Processes an audio recording from the customer microphone via Gemini transcription."""
    session = ACTIVE_CALL_SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"Call session '{session_id}' not found or expired.")
    return session.process_audio_turn(audio_bytes, mime_type=mime_type, voice_name=voice_name, interrupted=interrupted)


def complete_customer_call(session_id: str) -> Dict[str, Any]:
    """Finalizes a call session and compiles the formal interview dossier."""
    session = ACTIVE_CALL_SESSIONS.get(session_id)
    if not session:
        raise ValueError(f"Call session '{session_id}' not found or expired.")
    result = session.complete_call()
    ACTIVE_CALL_SESSIONS.pop(session_id, None)
    return result

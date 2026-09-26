from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0.7)

def get_rejection_template(candidate_name: str, role: str, company: str,
                            hr_name: str = "[Your Name]") -> str:
    return f"""Hi {candidate_name},

Thank you for taking the time to apply for the {role} position and for sharing your profile with us.

We appreciate your interest in the role and enjoyed learning about your background and projects. After careful consideration, we have decided to move forward with other candidates whose experience more closely matches our current requirements.

This was a competitive process, and we truly appreciate the effort you put into your application. We encourage you to continue building your AI and LLM project experience, and we wish you the very best in your academic and professional journey.

Thank you again for your interest in our team, and we hope you find an opportunity that is a great fit for your skills and goals.

Best regards,
{hr_name}
{company}"""


def get_selection_template(candidate_name: str, role: str, company: str,
                            hr_name: str = "[Your Name]",
                            duration: str = "3/6 Months",
                            mode: str = "Remote/Hybrid/On-site",
                            joining_date: str = "[Date]",
                            stipend: str = "[Amount, if applicable]",
                            contact: str = "[Contact Information]") -> str:
    return f"""Hi {candidate_name},

Congratulations! We are pleased to inform you that you have been selected for the {role} position at {company}.

We were impressed by your hands-on experience with LLM projects, your technical skills, and your enthusiasm for building AI applications. We believe you will be a great addition to our team.

Internship Details:
- Role: {role}
- Duration: {duration}
- Mode: {mode}
- Joining Date: {joining_date}
- Stipend/Compensation: {stipend}

As part of the next steps, please reply to this email confirming your acceptance of the offer. We will then share the onboarding process and additional details.

We are excited to have you onboard and look forward to working together on impactful AI projects.

Welcome to the team!

Best regards,
{hr_name}
{company}
{contact}"""


def ai_personalize_email(base_template: str, candidate_name: str,
                          matched_skills: list, shortlist_reasoning: str) -> str:
    """Use LLM to add one personalized sentence referencing the candidate's actual strengths."""
    response = _llm().invoke([
        SystemMessage(content="""You are an HR email writer. 
You receive a template email and must add ONE personalized sentence after the first paragraph 
that references the candidate's specific skills/strengths. 
Return the FULL email with that sentence inserted. Change nothing else."""),
        HumanMessage(content=f"""
Template:
{base_template}

Candidate: {candidate_name}
Their strengths: {', '.join(matched_skills[:5]) if matched_skills else 'strong technical skills'}
AI assessment: {shortlist_reasoning}

Insert one personalized sentence referencing their actual strengths after the first paragraph.
Return the complete modified email only.""")
    ])
    return response.content.strip()


def send_email(to_address: str, subject: str, body: str,
               smtp_host: str, smtp_port: int,
               sender_email: str, sender_password: str) -> tuple[bool, str]:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = sender_email
        msg["To"]      = to_address

        html_body = body.replace("\n", "<br>").replace("•", "&bull;")
        html = f"""<html><body style="font-family: Arial, sans-serif; line-height: 1.7;
                        color: #333; max-width: 620px; margin: auto; padding: 24px;">
            <p>{html_body}</p>
            <hr style="border:none; border-top:1px solid #eee; margin:20px 0;">
            <p style="color:#aaa; font-size:11px;">
                Sent via Talent Intelligence System · Powered by AI
            </p>
        </body></html>"""

        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html,  "html"))

        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_address, msg.as_string())

        return True, f"✅ Email sent to {to_address}"
    except Exception as e:
        return False, f"❌ Failed: {str(e)}"
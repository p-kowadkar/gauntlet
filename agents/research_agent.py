import requests
from config import YOUCOM_API_KEY, YOUCOM_SEARCH_URL
from core.agent_base import AgentBase


def _search_domain_failures(domain: str, query: str) -> list[str]:
    """
    GET https://ydc-index.io/v1/search
    Auth: X-API-Key header
    Params: ?query=...&count=5  (query string, not JSON body)
    Response: results.web[].description + results.web[].snippets[]
    """
    try:
        resp = requests.get(
            YOUCOM_SEARCH_URL,
            params={"query": query, "count": 5},
            headers={"X-API-Key": YOUCOM_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        web_results = resp.json().get("results", {}).get("web", [])
        findings = []
        for r in web_results[:5]:
            desc = r.get("description", "")
            if desc:
                findings.append(desc)
            else:
                snippets = r.get("snippets", [])
                if snippets:
                    findings.append(snippets[0])
        return findings
    except Exception as e:
        return [f"Search unavailable: {str(e)}"]


def _search_compliance_risks(domain: str) -> list[str]:
    return _search_domain_failures(
        domain,
        f"{domain} AI agent compliance failure regulatory risk 2024 2025",
    )


def _search_known_exploits(domain: str) -> list[str]:
    return _search_domain_failures(
        domain,
        f"{domain} AI chatbot attack prompt injection jailbreak incident",
    )


class ResearchAgent(AgentBase):
    SKILLS = {
        "search_domain_failures":  _search_domain_failures,
        "search_compliance_risks": _search_compliance_risks,
        "search_known_exploits":   _search_known_exploits,
    }

    def run(self, context: dict) -> dict:
        domain = context["domain"]

        general    = self.invoke_skill(
            "search_domain_failures",
            domain=domain,
            query=f"{domain} enterprise AI agent failure hallucination error 2024 2025",
        )
        compliance = self.invoke_skill("search_compliance_risks", domain=domain)
        exploits   = self.invoke_skill("search_known_exploits",   domain=domain)

        all_findings = list({
            f for f in (general + compliance + exploits)
            if f and len(f) > 20
        })

        return {
            "research_findings": all_findings,
            "research_count":    len(all_findings),
        }

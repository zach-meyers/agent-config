# Threat boundary worksheet

| Boundary | Entry points | Authn/z | Sensitive data | Notes |
| -------- | ------------ | ------- | -------------- | ----- |
| Public web | | | | |
| Authenticated API | | | | |
| Internal services | | | | |
| Admin / staff | | | | |
| Third-party callbacks | | | | |

**Abuse scenarios to consider:** credential stuffing, token theft, IDOR, webhook spoofing, SSRF from outbound HTTP, log injection, dependency compromise.

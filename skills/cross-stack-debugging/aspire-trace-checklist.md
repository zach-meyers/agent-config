# Aspire trace checklist

Use when the defect appears only under local orchestration or service wiring.

- [ ] Confirm AppHost selects the same configuration profile as the reporter (Debug vs Release variants).
- [ ] Verify the failing service receives the expected connection string / endpoint from the resource graph.
- [ ] Check structured logs and traces for the request correlation id across projects.
- [ ] Compare direct service call vs routed call through the gateway or YARP front door if applicable.
- [ ] Rule out stale build artifacts before chasing application logic.

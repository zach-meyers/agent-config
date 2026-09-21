# Upgrade gate checklist

- [ ] Release notes read for each direct dependency
- [ ] Security advisories checked for old and new versions
- [ ] Central pin file updated (NuGet props / package.json policy)
- [ ] Lockfiles regenerated, not hand-edited
- [ ] Install scripts remain disabled unless user opted in
- [ ] Targeted tests pass
- [ ] Build / lint / typecheck pass (as applicable)
- [ ] Rollback point recorded (commit or branch)

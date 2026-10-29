from .skills import mentions, negative_mention, normalize_skill, skill_name


def analyze_candidate(snapshot):
    skills = {}

    def record(key, path, text, kind, start=0, end=None):
        entry = {
            "key": key,
            "name": skill_name(key),
            "kind": kind,
            "path": path,
            "text": text[:400],
            "start": start,
            "end": len(text) if end is None else end,
        }
        skills.setdefault(key, []).append(entry)

    for index, item in enumerate(snapshot.get("skills", [])):
        record(normalize_skill(item["name"]), f"skills/{item['id']}", item["name"], "explicit")
    texts = []
    for field in ["headline", "summary"]:
        if snapshot.get(field):
            texts.append((field, snapshot[field]))
    for field in ["projects", "qualifications", "certifications"]:
        texts.extend((f"{field}/{i}", value) for i, value in enumerate(snapshot.get(field, [])))
    for experience in snapshot.get("experience", []):
        ref = f"experience/{experience['id']}"
        for technology in experience.get("technologies", []):
            record(normalize_skill(technology), ref + "/technologies", technology, "explicit")
        texts.extend(
            (ref + "/" + field, experience[field])
            for field in ["title", "responsibilities", "achievements"]
            if experience.get(field)
        )
    for path, text in texts:
        for key, (start, end, _) in mentions(text).items():
            if not negative_mention(text, start):
                # Store an exact span; text is not a generated qualification.
                record(key, path, text[start:end], "derived", start, end)
    roles = []
    prefs = snapshot.get("preferences") or {}
    for i, title in enumerate(prefs.get("target_titles", [])):
        roles.append({"text": title, "path": f"preferences/target_titles/{i}", "kind": "explicit"})
    if snapshot.get("headline"):
        roles.append({"text": snapshot["headline"], "path": "headline", "kind": "explicit"})
    for item in snapshot.get("experience", []):
        roles.append(
            {"text": item["title"], "path": f"experience/{item['id']}/title", "kind": "explicit"}
        )
    completeness = "skills_only" if skills else "insufficient"
    if skills and snapshot.get("experience"):
        completeness = "skills_and_experience"
    if (
        skills
        and snapshot.get("experience")
        and any(prefs.get(k) for k in ["target_titles", "locations", "work_arrangements"])
    ):
        completeness = "skills_experience_preferences"
    if (
        completeness == "skills_experience_preferences"
        and snapshot.get("education")
        and snapshot.get("projects")
    ):
        completeness = "broader_profile"
    if not skills and snapshot.get("experience"):
        completeness = "experience_only"
    elif not skills and snapshot.get("projects"):
        completeness = "projects_only"
    return {
        "skills": skills,
        "roles": roles,
        "experience": snapshot.get("experience", []),
        "education": snapshot.get("education", []),
        "qualifications": snapshot.get("qualifications", []),
        "certifications": snapshot.get("certifications", []),
        "projects": snapshot.get("projects", []),
        "preferences": prefs,
        "completeness": completeness,
        "professional_evidence_present": bool(
            skills or snapshot.get("experience") or snapshot.get("projects")
        ),
    }

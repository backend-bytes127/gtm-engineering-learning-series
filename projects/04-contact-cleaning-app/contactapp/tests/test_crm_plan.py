from contactapp import crm_plan, service


def row(**kw):
    base = {"Company Name": "Acme", "Website": "acme.com", "HQ Location": "Dubai, United Arab Emirates", "Company Size": "51-200",
            "Contact Person Name": "A B", "First Name": "A", "Last Name": "B", "Designation/Job Title": "CEO",
            "LinkedIn URL": "", "Mobile No.": "", "Email ID": "a@acme.com"}
    return {**base, **kw}


def test_blank_fields_are_never_sent():
    plan = crm_plan.build_plan([row()])
    assert "hs_linkedin_url" not in plan.contacts[0].properties and "mobilephone" not in plan.contacts[0].properties


def test_company_is_split_into_city_country_and_keeps_size_bucket():
    c = crm_plan.build_plan([row()]).companies[0].properties
    assert (c["city"], c["country"], c["gtm_company_size"], c["domain"]) == ("Dubai", "United Arab Emirates", "51-200", "acme.com")


def test_row_without_email_is_skipped_with_a_reason():
    plan = crm_plan.build_plan([row(**{"Email ID": ""})])
    assert not plan.contacts and "e-mail" in plan.skipped[0].reason


def test_duplicate_email_is_skipped_case_insensitively():
    plan = crm_plan.build_plan([row(), row(**{"Email ID": "A@Acme.com"})])
    assert len(plan.contacts) == 1 and len(plan.skipped) == 1


def test_companies_are_unique_by_domain_and_contacts_link_to_them():
    plan = crm_plan.build_plan([row(), row(**{"Email ID": "c@acme.com"}), row(**{"Email ID": "d@x.com", "Website": ""})])
    assert len(plan.companies) == 1 and plan.associations == 2


def test_the_sample_plan_covers_every_person():
    plan = crm_plan.build_plan(service.run_sample().rows)
    assert (len(plan.contacts), len(plan.companies), len(plan.skipped)) == (12, 5, 0)


def test_preview_is_json_ready():
    import json

    json.dumps(crm_plan.preview(crm_plan.build_plan([row()])))

"""Coverage tests for global_knowledge listed arcs in analyze_global_impact/_get_learning_recommendations."""

from __future__ import annotations

from unittest.mock import patch

from ai_knowledge.expansion.global_knowledge import GlobalExpertiseUpdater, GlobalKnowledgeConnector

AUTO_OK = {"success": True, "data": {"electric_vehicles": {"trend": "t"}}}
EQUIP_OK = {"success": True, "data": {"construction_boom": {"trend": "t"}}}
TAX_OK = {"success": True, "data": {"uae_vat": {}}}
AUTO_FAIL = {"success": False, "error": "down"}
EQUIP_FAIL = {"success": False, "error": "down"}
TAX_FAIL = {"success": False, "error": "down"}


def _insights(auto, equip, tax):
    return {"automotive_trends": auto, "equipment_trends": equip, "tax_updates": tax}


def _impact(auto, equip, tax):
    connector = GlobalKnowledgeConnector()
    with patch.object(GlobalKnowledgeConnector, "get_global_insights", return_value=_insights(auto, equip, tax)):
        return connector.analyze_global_impact({})


def test_cov_gk_auto_fail_skips_to_equipment():
    """Arc 221->236: automotive success False jumps to equipment block."""
    result = _impact(AUTO_FAIL, EQUIP_OK, TAX_OK)
    assert any(o["area"] == "المعدات الثقيلة" for o in result["opportunities"])
    assert not any(o["area"] == "السيارات الكهربائية" for o in result["opportunities"])


def test_cov_gk_auto_without_electric_skips_to_equipment():
    """Arc 225->236: automotive ok but no electric_vehicles key."""
    auto = {"success": True, "data": {"other": {}}}
    result = _impact(auto, EQUIP_OK, TAX_OK)
    assert not any(o["area"] == "السيارات الكهربائية" for o in result["opportunities"])


def test_cov_gk_auto_with_electric_true_side():
    """True side of 225: electric_vehicles appends an opportunity."""
    result = _impact(AUTO_OK, EQUIP_FAIL, TAX_FAIL)
    assert any(o["area"] == "السيارات الكهربائية" for o in result["opportunities"])


def test_cov_gk_equipment_fail_skips_to_tax():
    """Arc 236->250: equipment success False jumps to tax block."""
    result = _impact(AUTO_OK, EQUIP_FAIL, TAX_OK)
    assert any(o["area"] == "السيارات الكهربائية" for o in result["opportunities"])
    assert not any(o["area"] == "المعدات الثقيلة" for o in result["opportunities"])
    assert result["recommendations"] != []


def test_cov_gk_equipment_without_boom_skips_to_tax():
    """Arc 239->250: equipment ok but no construction_boom key."""
    equip = {"success": True, "data": {"other": {}}}
    result = _impact(AUTO_FAIL, equip, TAX_OK)
    assert not any(o["area"] == "المعدات الثقيلة" for o in result["opportunities"])
    assert result["recommendations"] != []


def test_cov_gk_tax_fail_returns_without_recommendations():
    """Arc 250->259: tax success False skips recommendations."""
    result = _impact(AUTO_FAIL, EQUIP_FAIL, TAX_FAIL)
    assert result["opportunities"] == []
    assert result["recommendations"] == []


def _recs(area, auto=None, equip=None, tax=None):
    insights = {
        "automotive_trends": auto if auto is not None else AUTO_FAIL,
        "equipment_trends": equip if equip is not None else EQUIP_FAIL,
        "tax_updates": tax if tax is not None else TAX_FAIL,
    }
    return GlobalExpertiseUpdater._get_learning_recommendations(area, insights)


def test_cov_gk_auto_recs_trends_fail():
    """Arc 358->405: automotive area with failed trends returns []."""
    assert _recs("automotive") == []


def test_cov_gk_auto_recs_only_autonomous():
    """Arc 361->371: no electric key, autonomous present."""
    auto = {"success": True, "data": {"autonomous_vehicles": {}}}
    recs = _recs("automotive", auto=auto)
    assert [r["topic"] for r in recs] == ["السيارات ذاتية القيادة"]


def test_cov_gk_auto_recs_only_electric():
    """Arc 371->405: electric present, no autonomous key."""
    auto = {"success": True, "data": {"electric_vehicles": {}}}
    recs = _recs("automotive", auto=auto)
    assert [r["topic"] for r in recs] == ["السيارات الكهربائية"]


def test_cov_gk_auto_recs_both_present():
    """True sides of 361+371: both topics recommended."""
    auto = {"success": True, "data": {"electric_vehicles": {}, "autonomous_vehicles": {}}}
    recs = _recs("automotive", auto=auto)
    assert len(recs) == 2


def test_cov_gk_heavy_recs_trends_fail():
    """Arc 382->405: heavy_equipment area with failed trends returns []."""
    assert _recs("heavy_equipment") == []


def test_cov_gk_heavy_recs_without_digitalization():
    """Arc 385->405: equipment ok but no digitalization key."""
    equip = {"success": True, "data": {"other": {}}}
    assert _recs("heavy_equipment", equip=equip) == []


def test_cov_gk_heavy_recs_with_digitalization():
    """True side of 385: digitalization recommended."""
    equip = {"success": True, "data": {"digitalization": {}}}
    recs = _recs("heavy_equipment", equip=equip)
    assert [r["topic"] for r in recs] == ["رقمنة المعدات"]


def test_cov_gk_tax_recs_fail_and_unknown_area():
    """Arc 395->405: tax success False and unknown area return []."""
    assert _recs("tax_regulations") == []
    assert _recs("unknown_area") == []
    recs = _recs("tax_regulations", tax=TAX_OK)
    assert [r["topic"] for r in recs] == ["التحديثات الضريبية"]

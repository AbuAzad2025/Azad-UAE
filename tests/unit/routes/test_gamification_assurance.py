from __future__ import annotations


class TestGamificationRoutes:
    def test_leaderboard_renders_template(self, auth_client, mocker):
        board = [{"user": "alice", "points": 100}]
        mocker.patch(
            "routes.gamification.GamificationService.get_leaderboard",
            return_value=board,
        )
        mocker.patch(
            "routes.gamification.render_template",
            return_value="leaderboard-html",
        )
        resp = auth_client.get("/gamification/leaderboard")
        assert resp.status_code == 200

    def test_my_stats_returns_json(self, auth_client, mocker):
        stats = {"points": 50, "rank": 3}
        mocker.patch(
            "routes.gamification.GamificationService.get_user_stats",
            return_value=stats,
        )
        resp = auth_client.get("/gamification/my-stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"] == stats

    def test_award_points_returns_result(self, auth_client, mocker):
        result = {"awarded": 10, "action": "sale"}
        mocker.patch(
            "routes.gamification.GamificationService.award_points",
            return_value=result,
        )
        resp = auth_client.post("/gamification/award/sale")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"] == result

    def test_routes_require_login(self, client):
        for path in ("/gamification/leaderboard", "/gamification/my-stats"):
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403)
        # The award endpoint is POST-only (CSRF-covered); an anonymous POST
        # must be refused just like the read surfaces.
        resp = client.post("/gamification/award/login")
        assert resp.status_code in (302, 401, 403)

    def test_award_points_passes_user_id(self, auth_client, mocker, sample_user):
        award = mocker.patch(
            "routes.gamification.GamificationService.award_points",
            return_value={"ok": True},
        )
        auth_client.post("/gamification/award/daily_login")
        award.assert_called_once()
        assert award.call_args[0][0] == sample_user.id
        assert award.call_args[0][1] == "daily_login"

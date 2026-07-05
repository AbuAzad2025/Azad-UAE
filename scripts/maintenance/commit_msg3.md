Fix test_csrf_token_protection_in_ajax to exclude public JS files

support.js handles public donation/payment endpoints that do not
require CSRF tokens (unauthenticated routes). The test was
incorrectly flagging legitimate public-facing fetch() POST calls.

Generated with Devin (https://cli.devin.ai/docs)
Co-Authored-By: Devin <158243242+devin-ai-integration[bot]@users.noreply.github.com>

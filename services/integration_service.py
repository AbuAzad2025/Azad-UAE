from models.integration_settings import IntegrationSettings

class IntegrationService:
    @staticmethod
    def get_integrations_context():
        whatsapp = IntegrationSettings.get_service_config('whatsapp')
        email = IntegrationSettings.get_service_config('email')
        redis = IntegrationSettings.get_service_config('redis')
        currency_api = IntegrationSettings.get_service_config('currency_api')

        return {
            'whatsapp': {
                'enabled': whatsapp.enabled,
                'config': whatsapp.get_config(),
                'last_tested': whatsapp.last_tested_at,
                'status': whatsapp.last_test_status or 'not_configured'
            },
            'email': {
                'enabled': email.enabled,
                'config': email.get_config(),
                'last_tested': email.last_tested_at,
                'status': email.last_test_status or 'not_configured'
            },
            'redis': {
                'enabled': redis.enabled,
                'config': redis.get_config(),
                'last_tested': redis.last_tested_at,
                'status': redis.last_test_status or 'not_configured'
            },
            'currency_api': {
                'enabled': currency_api.enabled,
                'config': currency_api.get_config(),
                'last_tested': currency_api.last_tested_at,
                'status': currency_api.last_test_status or 'not_configured'
            }
        }

import pytest
from unittest.mock import MagicMock, patch
from services.integration_service import IntegrationService

def test_get_integrations_context_structure():
    # Mock IntegrationSettings.get_service_config
    with patch('services.integration_service.IntegrationSettings.get_service_config') as mock_get_config:
        # Mock service config object
        mock_service = MagicMock()
        mock_service.enabled = True
        mock_service.get_config.return_value = {'key': 'value'}
        mock_service.last_tested_at = '2026-06-08'
        mock_service.last_test_status = 'success'
        
        mock_get_config.return_value = mock_service
        
        context = IntegrationService.get_integrations_context()
        
        # Verify structure
        for service in ['whatsapp', 'email', 'redis', 'currency_api']:
            assert service in context
            assert context[service]['enabled'] == True
            assert context[service]['config'] == {'key': 'value'}
            assert context[service]['last_tested'] == '2026-06-08'
            assert context[service]['status'] == 'success'
            
        assert mock_get_config.call_count == 4

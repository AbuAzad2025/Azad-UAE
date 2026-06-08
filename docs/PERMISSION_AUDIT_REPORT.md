# Permission Consistency Audit Report

**Routes scanned:** 497  
**Template links scanned:** 1235  
**Safe:** 1084  
**Gaps:** 0  
**Hidden:** 171  
**Unauth:** 0  

---


## LOW Severity (171)

- **`admin_ledger.api_account_balance`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\admin_ledger.py:435
  - Template conditions: 

- **`admin_ledger.api_account_statement`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\admin_ledger.py:450
  - Template conditions: 

- **`admin_ledger.balance_sheet`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\admin_ledger.py:361
  - Template conditions: 

- **`admin_ledger.income_statement`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\admin_ledger.py:394
  - Template conditions: 

- **`admin_ledger.settings`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\admin_ledger.py:428
  - Template conditions: 

- **`admin_ledger.trial_balance`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\admin_ledger.py:322
  - Template conditions: 

- **`advanced_ledger.advanced_analytics`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:504
  - Template conditions: 

- **`advanced_ledger.api_financial_ratios`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:520
  - Template conditions: 

- **`advanced_ledger.api_forecasting`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:554
  - Template conditions: 

- **`advanced_ledger.api_trend_analysis`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:540
  - Template conditions: 

- **`advanced_ledger.approve_journal_entry`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:326
  - Template conditions: 

- **`advanced_ledger.cheque_accounting_summary_api`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:452
  - Template conditions: 

- **`advanced_ledger.cheque_integration`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:350
  - Template conditions: 

- **`advanced_ledger.clear_cheque`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:391
  - Template conditions: 

- **`advanced_ledger.delete_journal_entry`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:302
  - Template conditions: 

- **`advanced_ledger.events_stream_api`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:433
  - Template conditions: 

- **`advanced_ledger.journal_management`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:263
  - Template conditions: 

- **`advanced_ledger.professional_printing`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:26
  - Template conditions: 

- **`advanced_ledger.professional_reports`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:469
  - Template conditions: 

- **`advanced_ledger.real_time_events`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:416
  - Template conditions: 

- **`advanced_ledger.receive_cheque`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\advanced_ledger.py:371
  - Template conditions: 

- **`ai.add_customer`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3706
  - Template conditions: 

- **`ai.add_knowledge_document`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3795
  - Template conditions: 

- **`ai.add_knowledge_website`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3769
  - Template conditions: 

- **`ai.analyze_customer`** — HIDDEN
  - Route guards: login_required, view_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:296
  - Template conditions: 

- **`ai.analyze_customer_debt`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3640
  - Template conditions: 

- **`ai.analyze_margins`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3326
  - Template conditions: 

- **`ai.analyze_product_performance`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3738
  - Template conditions: 

- **`ai.analyze_sales_performance`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3722
  - Template conditions: 

- **`ai.ask_genius`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3943
  - Template conditions: 

- **`ai.auto_improve`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3497
  - Template conditions: 

- **`ai.automotive_ecu_code`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3879
  - Template conditions: 

- **`ai.automotive_sensor`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3899
  - Template conditions: 

- **`ai.cash_flow_prediction`** — HIDDEN
  - Route guards: login_required, view_ledger
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3362
  - Template conditions: 

- **`ai.check_stock`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:276
  - Template conditions: 

- **`ai.churn_prediction`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3393
  - Template conditions: 

- **`ai.contextual_help`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3433
  - Template conditions: 

- **`ai.deep_analysis`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3353
  - Template conditions: 

- **`ai.detect_patterns`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3335
  - Template conditions: 

- **`ai.evolve_knowledge`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3461
  - Template conditions: 

- **`ai.exchange_rate`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:309
  - Template conditions: 

- **`ai.external_sources`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3919
  - Template conditions: 

- **`ai.find_compatible`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:336
  - Template conditions: 

- **`ai.get_customer_balance`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3625
  - Template conditions: 

- **`ai.get_financial_ratios`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3754
  - Template conditions: 

- **`ai.get_knowledge_summary`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3846
  - Template conditions: 

- **`ai.get_product_stock`** — HIDDEN
  - Route guards: login_required, manage_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3655
  - Template conditions: 

- **`ai.get_system_summary`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3670
  - Template conditions: 

- **`ai.global_insights`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3559
  - Template conditions: 

- **`ai.improvement_progress`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3515
  - Template conditions: 

- **`ai.improvement_status`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3479
  - Template conditions: 

- **`ai.inventory_health`** — HIDDEN
  - Route guards: login_required, manage_warehouse
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3344
  - Template conditions: 

- **`ai.learning_status`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3443
  - Template conditions: 

- **`ai.neural_status`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3861
  - Template conditions: 

- **`ai.optimize_inventory`** — HIDDEN
  - Route guards: login_required, manage_warehouse
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3402
  - Template conditions: 

- **`ai.performance_analysis`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3595
  - Template conditions: 

- **`ai.predict_sales`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3316
  - Template conditions: 

- **`ai.quick_calc`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3977
  - Template conditions: 

- **`ai.recommend_price`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:255
  - Template conditions: 

- **`ai.search_knowledge`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3822
  - Template conditions: 

- **`ai.search_market_price`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:318
  - Template conditions: 

- **`ai.search_system_data`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3691
  - Template conditions: 

- **`ai.set_improvement_goal`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3533
  - Template conditions: 

- **`ai.smart_price`** — HIDDEN
  - Route guards: login_required, view_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3372
  - Template conditions: 

- **`ai.transformers_understand`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:4007
  - Template conditions: 

- **`ai.update_global_expertise`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ai.py:3577
  - Template conditions: 

- **`api.check_username`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api.py:425
  - Template conditions: 

- **`api.currencies`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api.py:281
  - Template conditions: 

- **`api.currency_rate`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api.py:248
  - Template conditions: 

- **`api.echo`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api.py:512
  - Template conditions: 

- **`api.payment_fields`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api.py:195
  - Template conditions: 

- **`api.products_low_stock`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api.py:457
  - Template conditions: 

- **`api_analytics.daily_stats`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_analytics.py:40
  - Template conditions: 

- **`api_analytics.low_stock_products`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_analytics.py:108
  - Template conditions: 

- **`api_analytics.overdue_payments`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_analytics.py:18
  - Template conditions: 

- **`api_analytics.revenue_trend`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_analytics.py:137
  - Template conditions: 

- **`api_analytics.top_customers`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_analytics.py:79
  - Template conditions: 

- **`api_enhanced.get_customers`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_enhanced.py:68
  - Template conditions: 

- **`api_enhanced.get_sale`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_enhanced.py:46
  - Template conditions: 

- **`api_enhanced.get_sales`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_enhanced.py:17
  - Template conditions: 

- **`api_enhanced.profit_margins`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_enhanced.py:142
  - Template conditions: 

- **`api_enhanced.sales_forecast`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_enhanced.py:129
  - Template conditions: 

- **`api_enhanced.search_products`** — HIDDEN
  - Route guards: login_required, manage_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\api_enhanced.py:94
  - Template conditions: 

- **`branches.delete`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\branches.py:107
  - Template conditions: 

- **`cheques.api_alerts`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\cheques.py:746
  - Template conditions: 

- **`cheques.api_stats`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\cheques.py:735
  - Template conditions: 

- **`cheques.archived`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\cheques.py:714
  - Template conditions: 

- **`cheques.delete`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\cheques.py:603
  - Template conditions: 

- **`customers.api_search`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\customers.py:662
  - Template conditions: 

- **`customers.customer_balance`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\customers.py:697
  - Template conditions: 

- **`customers.customer_sales`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\customers.py:725
  - Template conditions: 

- **`customers.delete`** — HIDDEN
  - Route guards: login_required, manage_customers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\customers.py:411
  - Template conditions: 

- **`expenses.archive`** — HIDDEN
  - Route guards: login_required, manage_expenses
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\expenses.py:513
  - Template conditions: 

- **`expenses.archived`** — HIDDEN
  - Route guards: login_required, manage_expenses
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\expenses.py:477
  - Template conditions: 

- **`expenses.categories`** — HIDDEN
  - Route guards: login_required, manage_expenses
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\expenses.py:419
  - Template conditions: 

- **`expenses.restore`** — HIDDEN
  - Route guards: login_required, manage_expenses
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\expenses.py:534
  - Template conditions: 

- **`gamification.award_points`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\gamification.py:24
  - Template conditions: 

- **`gamification.leaderboard`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\gamification.py:10
  - Template conditions: 

- **`gamification.my_stats`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\gamification.py:17
  - Template conditions: 

- **`graphql.graphql_playground`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\graphql.py:171
  - Template conditions: 

- **`graphql.graphql_query`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\graphql.py:95
  - Template conditions: 

- **`ledger.admin_accounts`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ledger.py:741
  - Template conditions: 

- **`ledger.admin_add_account`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ledger.py:750
  - Template conditions: 

- **`ledger.admin_settings`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ledger.py:952
  - Template conditions: 

- **`ledger.admin_vaults`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ledger.py:812
  - Template conditions: 

- **`ledger.api_calculate_journal_balance`** — HIDDEN
  - Route guards: login_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\ledger.py:582
  - Template conditions: 

- **`monitoring.dashboard`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\monitoring.py:27
  - Template conditions: 

- **`monitoring.metrics`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\monitoring.py:19
  - Template conditions: 

- **`owner.archived`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:455
  - Template conditions: 

- **`owner.backup_info`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:1223
  - Template conditions: 

- **`owner.config`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:817
  - Template conditions: 

- **`owner.execute_query`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:919
  - Template conditions: 

- **`owner.financial_overview`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:807
  - Template conditions: 

- **`owner.master_login_info`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:58
  - Template conditions: 

- **`owner.system_stats`** — HIDDEN
  - Route guards: login_required, owner_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\owner.py:407
  - Template conditions: 

- **`partners.add_transaction`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\partners.py:290
  - Template conditions: 

- **`partners.api_preview_pnl`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\partners.py:318
  - Template conditions: 

- **`payment_vault.api_package_stats`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1268
  - Template conditions: 

- **`payment_vault.api_v2_donations`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1724
  - Template conditions: 

- **`payment_vault.api_v2_purchases`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1663
  - Template conditions: 

- **`payment_vault.api_v2_stats`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1781
  - Template conditions: 

- **`payment_vault.decrypt_card`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:723
  - Template conditions: 

- **`payment_vault.delete_package`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:595
  - Template conditions: 

- **`payment_vault.donation_detail`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1303
  - Template conditions: 

- **`payment_vault.edit_package`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:526
  - Template conditions: 

- **`payment_vault.export_cards`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1474
  - Template conditions: 

- **`payment_vault.export_donations`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1455
  - Template conditions: 

- **`payment_vault.export_purchases`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1437
  - Template conditions: 

- **`payment_vault.export_report_pdf`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1492
  - Template conditions: 

- **`payment_vault.health_check`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1638
  - Template conditions: 

- **`payment_vault.process_payment`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:751
  - Template conditions: 

- **`payment_vault.system_metrics`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1650
  - Template conditions: 

- **`payment_vault.toggle_package_status`** — HIDDEN
  - Route guards: owner_only
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payment_vault.py:1286
  - Template conditions: 

- **`payments.api_customer_balance`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:1637
  - Template conditions: 

- **`payments.archive_payment`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:500
  - Template conditions: 

- **`payments.archive_receipt`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:1237
  - Template conditions: 

- **`payments.index`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:27
  - Template conditions: 

- **`payments.restore_payment`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:539
  - Template conditions: 

- **`payments.restore_receipt`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:1258
  - Template conditions: 

- **`payments.search_entities`** — HIDDEN
  - Route guards: login_required, manage_payments
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\payments.py:376
  - Template conditions: 

- **`pos.api_checkout`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\pos.py:164
  - Template conditions: 

- **`pos.api_customers`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\pos.py:102
  - Template conditions: 

- **`pos.api_product_lookup`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\pos.py:75
  - Template conditions: 

- **`pos.api_products`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\pos.py:55
  - Template conditions: 

- **`pos.api_walkin_customer`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\pos.py:140
  - Template conditions: 

- **`products.adjust_stock`** — HIDDEN
  - Route guards: login_required, manage_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\products.py:1028
  - Template conditions: 

- **`products.api_search`** — HIDDEN
  - Route guards: login_required, manage_sales, manage_purchases, manage_products, any_permission_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\products.py:908
  - Template conditions: 

- **`products.categories`** — HIDDEN
  - Route guards: login_required, manage_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\products.py:949
  - Template conditions: 

- **`products.delete`** — HIDDEN
  - Route guards: login_required, manage_products
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\products.py:865
  - Template conditions: 

- **`purchases.delete`** — HIDDEN
  - Route guards: login_required, manage_purchases
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\purchases.py:218
  - Template conditions: 

- **`reports.api_entity_search`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\reports.py:1456
  - Template conditions: 

- **`reports.api_model_fields`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\reports.py:1424
  - Template conditions: 

- **`reports.entity_report_fragment`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\reports.py:1508
  - Template conditions: 

- **`reports.index`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\reports.py:54
  - Template conditions: 

- **`reports.purchases`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\reports.py:543
  - Template conditions: 

- **`reports.top_selling`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\reports.py:1808
  - Template conditions: 

- **`returns.api_create_return`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\returns.py:62
  - Template conditions: 

- **`sales.api_calculate_sale_totals`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\sales.py:599
  - Template conditions: 

- **`sales.api_get_price`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\sales.py:403
  - Template conditions: 

- **`sales.archive`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\sales.py:542
  - Template conditions: 

- **`sales.restore`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\sales.py:569
  - Template conditions: 

- **`suppliers.api_search`** — HIDDEN
  - Route guards: login_required, manage_suppliers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\suppliers.py:407
  - Template conditions: 

- **`suppliers.delete`** — HIDDEN
  - Route guards: login_required, manage_suppliers
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\suppliers.py:335
  - Template conditions: 

- **`treasury.vat_return`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\treasury.py:104
  - Template conditions: 

- **`treasury.wps_export`** — HIDDEN
  - Route guards: login_required, view_reports
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\treasury.py:116
  - Template conditions: 

- **`users.delete`** — HIDDEN
  - Route guards: login_required, manage_users
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\users.py:331
  - Template conditions: 

- **`warehouse.add_stock`** — HIDDEN
  - Route guards: login_required, manage_warehouse
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\warehouse.py:425
  - Template conditions: 

- **`warehouse.delete_warehouse`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\warehouse.py:392
  - Template conditions: 

- **`whatsapp.send_invoice`** — HIDDEN
  - Route guards: login_required, manage_sales
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\whatsapp.py:12
  - Template conditions: 

- **`whatsapp.send_reminder`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\whatsapp.py:47
  - Template conditions: 

- **`whatsapp.test_connection`** — HIDDEN
  - Route guards: login_required, admin_required
  - Template: D:\Data\karaj\UAE\Azad-UAE\routes\whatsapp.py:82
  - Template conditions: 

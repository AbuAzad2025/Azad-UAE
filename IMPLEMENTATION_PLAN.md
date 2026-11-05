# Implementation Plan: Product Import Enhancement Features

## Phase 1: Background Job Infrastructure (HIGH)
- [ ] Create `ProductImportJob` model for tracking import jobs
- [ ] Create `ProductImportTemplate` model for saved column mappings
- [ ] Create `services/import_job_service.py` for background job management
- [ ] Create Celery tasks for background product import
- [ ] Add WebSocket progress events via Flask-SocketIO

## Phase 2: Import Service Enhancement (HIGH)
- [ ] Create `services/product_import_service.py` with:
  - Dry-run preview functionality
  - Template mapping support
  - Background job integration
  - Progress tracking
  - Rollback capability
- [ ] Update `routes/products.py` to use new service

## Phase 3: API & Frontend (MEDIUM)
- [ ] Create `/api/products/bulk` endpoint
- [ ] Add WebSocket progress events
- [ ] Update templates for progress bar and dry-run preview
- [ ] Add rollback button UI

## Phase 4: OCR & Mobile (HIGH)
- [ ] Create `services/ocr_service.py` for invoice/box OCR
- [ ] Create mobile app structure (Flutter/React Native)
- [ ] Add barcode scanner API endpoints

## Phase 5: Testing & Integration
- [ ] Unit tests for all new services
- [ ] Integration tests for background jobs
- [ ] WebSocket integration tests
- [ ] Update documentation

---

## Implementation Order (Priority)

1. **Models** - `ProductImportJob`, `ProductImportTemplate`
2. **Background Job Service** - `ImportJobService`, Celery tasks
3. **Import Service** - `ProductImportService` with dry-run, template mapping
4. **Routes** - Updated import routes with background job support
5. **WebSocket** - Progress events via Flask-SocketIO
6. **Templates** - Updated UI with progress bar, dry-run, rollback
6. **API** - `/api/products/bulk` endpoint
7. **OCR Service** - Invoice/box OCR
8. **Mobile API** - Barcode scanner endpoints
9. **Tests** - Unit and integration tests
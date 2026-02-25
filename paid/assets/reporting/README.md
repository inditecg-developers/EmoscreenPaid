# Paid report assets

Place paid-report branding assets here.

## Logo locations checked by the PDF generator

When `es_cfg_report_templates.header_logo_path` is configured (for example `logo_eq_final.jpeg`),
the renderer will resolve it in this order:

1. Absolute path (if provided)
2. `<BASE_DIR>/<header_logo_path>`
3. `<BASE_DIR>/paid/assets/reporting/logos/<filename>`
4. `<BASE_DIR>/static/paid/reporting/logos/<filename>`
5. `<MEDIA_ROOT>/<header_logo_path>`

Recommended: copy your logo to `paid/assets/reporting/logos/logo_eq_final.jpeg`.

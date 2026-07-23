/**
 * OHIF app configuration for the MSXplain deployment.
 *
 * Design constraints (see docker-compose + backend/app.py):
 *   - OHIF is served same-origin at /viewer/ and reads images ONLY from the
 *     backend's read-only DICOMweb proxy at /api/dicom-web. It never talks to
 *     Orthanc directly and has no other data source.
 *   - Authentication is handled transparently by an HttpOnly cookie (`dcmw`)
 *     that the main app sets via POST /api/viewer-session before opening the
 *     viewer. Because requests are same-origin, the browser attaches the cookie
 *     automatically — OHIF needs no token/OIDC wiring here.
 *   - Download/export surfaces are removed so a user cannot one-click save the
 *     source data. (Raw pixels still reach the browser to render — that is an
 *     accepted, documented residual risk.)
 */
window.config = {
  routerBasename: '/viewer/',
  // We always deep-link to a specific study (StudyInstanceUIDs=...), so the
  // study-list browser (a browse/enumerate + export surface) is disabled.
  showStudyList: false,
  extensions: [],
  modes: [],
  // No investigational-use nag for an internal clinical tool.
  investigationalUseDialog: { option: 'never' },
  defaultDataSourceName: 'dicomweb',
  dataSources: [
    {
      friendlyName: 'MSXplain PACS (read-only proxy)',
      namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
      sourceName: 'dicomweb',
      configuration: {
        name: 'orthanc',
        // Same-origin proxy — cookie auth is attached automatically.
        wadoUriRoot: '/api/dicom-web',
        qidoRoot: '/api/dicom-web',
        wadoRoot: '/api/dicom-web',
        qidoSupportsIncludeField: true,
        supportsReject: false,
        imageRendering: 'wadors',
        thumbnailRendering: 'wadors',
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: false,
        supportsWildcard: true,
        omitQuotationForMultipartRequest: true,
        // Read-only: never advertise STOW (upload) to the UI.
        supportsStow: false,
        // Same-origin requests already send the cookie; no CORS credentials
        // dance is needed.
        requestOptions: {},
      },
    },
    // NOTE: the `local` (drag-and-drop file) data source is intentionally NOT
    // registered, so users cannot side-load arbitrary studies.
  ],
  // Hide export/download affordances. These customizationService keys remove
  // the study-browser download action and the segmentation/measurement export
  // panels. Toolbar-level "Download/Capture" removal depends on the active
  // mode; verify against the pinned OHIF image and extend here if any export
  // control remains visible.
  customizationService: {
    'ohif.studyBrowser.customContextMenu': { menuItems: [] },
    'ohif.disableExport': true,
  },
};

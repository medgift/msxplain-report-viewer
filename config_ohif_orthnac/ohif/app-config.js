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
  // Hide export/download affordances (OHIF 3.13 customization API; the 3.9
  // keys `ohif.disableExport` / `ohif.studyBrowser.customContextMenu` no longer
  // exist). Applied in the `global` phase, i.e. after extensions register their
  // defaults and before the mode seeds its toolbar from them.
  customizationService: {
    global: {
      // "Capture" opens the viewport screenshot/download modal — drop it from
      // both the default and the segmentation-mode toolbars.
      'cornerstone.toolbarSections': {
        primary: { $apply: ids => ids.filter(id => id !== 'Capture') },
      },
      'cornerstone.segmentationToolbarSections': {
        primary: { $apply: ids => (ids || []).filter(id => id !== 'Capture') },
      },
      // Segmentations are our read-only outputs: no editing, no adding segments.
      'panelSegmentation.disableEditing': { $set: true },
      'panelSegmentation.showAddSegment': { $set: false },
      // The per-segmentation "..." menu holds Export (DICOM SEG / RTSS / CSV
      // download, store) plus create/rename/delete — replace it with nothing.
      'panelSegmentation.customDropdownMenuContent': { $set: () => null },
    },
  },
};

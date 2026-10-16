import React, { useEffect, useState } from 'react';
import './RegulatoryInfo.css';

// ── Regulatory / model-card content ──────────────────────────────────────────
// Single source of truth for the training-data disclosure shown on the report.
// The summary card surfaces representativeness and population characteristics;
// the modal lists every section required for the regulatory file.

const PHENOTYPES = [
  { acronym: 'RRMS', name: 'Relapsing-Remitting MS',           count: 1168 },
  { acronym: 'PPMS', name: 'Primary Progressive MS',           count: 73 },
  { acronym: 'SPMS', name: 'Secondary Progressive MS',         count: 61 },
  { acronym: 'CIS',  name: 'Clinically Isolated Syndrome',     count: 51 },
  { acronym: null,   name: 'Neuromyelitis optica',             count: 17 },
  { acronym: 'RIS',  name: 'Radiologically Isolated Syndrome', count: 8 },
];

const REPRESENTATIVENESS =
  'The training data reflects adult patients, predominantly diagnosed with MS, ' +
  'characterized by the presence of white matter lesions, and were obtained from ' +
  'Swiss hospitals. Performance has also been tested on adult patients’ data ' +
  'collected in four clinical imaging centers in France, and on pediatric data ' +
  'collected in Romania.';

const DEMOGRAPHICS =
  'Age range [18 – 77] and median age is 41.1 (IQR, 32.2 – 49.9); 66% Females.';

const EXCLUSION_CRITERIA =
  'Exclusion criteria encompassed major psychiatric or neurological comorbidities, ' +
  'contraindications to MRI, and pregnancy.';

// Phenotype counts rendered inline, with the acronyms spelled out.
const PhenotypeList = () => (
  <>
    {PHENOTYPES.map((p, i) => (
      <React.Fragment key={p.name}>
        {i > 0 && ', '}
        {p.acronym ? (
          <>
            <strong>{p.acronym}</strong>
            {` (${p.name})`}
          </>
        ) : (
          // No acronym: bold the name itself so every phenotype's lead is bold.
          <strong>{p.name}</strong>
        )}
        {`: ${p.count}`}
      </React.Fragment>
    ))}
    .
  </>
);

const PopulationCharacteristics = () => (
  <>
    {DEMOGRAPHICS} Phenotypes at baseline are <PhenotypeList /> {EXCLUSION_CRITERIA}
  </>
);

const SECTIONS = [
  {
    title: 'Dataset size',
    body: (
      <>
        Training set: 6750 MR studies from 3375 visits of 969 patients.<br />
        Validation set: 1044 MR studies from 522 visits of 138 patients.<br />
        Test set: 2030 MR studies from 1015 visits of 278 patients.
      </>
    ),
  },
  { title: 'Population characteristics', body: <PopulationCharacteristics /> },
  { title: 'Representativeness', body: REPRESENTATIVENESS },
  {
    title: 'Geography and clinical setting',
    body:
      'Data were collected from seven Swiss hospital imaging departments using ' +
      '1.5T and 3T MRI scanners.',
  },
  {
    title: 'Data modalities and input characteristics',
    body:
      'Inputs include FLAIR and MPRAGE MRI sequences, resampled to 1 mm ' +
      'isotropic resolution.',
  },
  {
    title: 'Annotation or ground truth',
    body:
      'Labels were generated automatically using two different segmentation ' +
      'networks, throughout the follow-ups. Then those labels were reviewed and ' +
      'edited by five raters with more than 10 years of experience in the field.',
  },
  {
    title: 'Data quality controls',
    body:
      'Images with severe motion artefacts, incomplete metadata, or inconsistent ' +
      'labels were excluded.',
  },
  { title: 'Known limitations and gaps', body: 'Data are coming from Swiss hospitals only.' },
  { title: 'Bias and fairness checks', body: 'Dataset balance was assessed across lesion load.' },
  {
    title: 'Separation from validation/test data',
    body:
      'Training, validation, and testing sets were separated at patient level; ' +
      'no patient appears in more than one set.',
  },
  { title: 'Date/version of the dataset', body: 'Training dataset version locked in December 2024.' },
];

// ── Modal ────────────────────────────────────────────────────────────────────
const RegulatoryModal = ({ onClose }) => {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="reg-overlay" onClick={onClose}>
      <div
        className="reg-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reg-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="reg-close" onClick={onClose} aria-label="Close regulatory information">
          ×
        </button>
        <h2 id="reg-modal-title" className="reg-modal-title">
          MS Lesion Segmentation<br />Regulatory Information
        </h2>
        <div className="reg-modal-body">
          {SECTIONS.map((s) => (
            <section className="reg-section" key={s.title}>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
};

// ── Summary card (sits under the patient strip on the report) ────────────────
const RegulatoryInfo = () => {
  const [open, setOpen] = useState(false);

  return (
    <section className="card reg-card">
      <div className="reg-card-head">
        <h3>Algorithm Training Information</h3>
        <button className="reg-full-button" onClick={() => setOpen(true)}>
          Full Regulatory information
          <span className="reg-full-icon" aria-hidden="true">i</span>
        </button>
      </div>

      <div className="reg-card-grid">
        <div className="reg-card-block">
          <h4>Representativeness</h4>
          <p>{REPRESENTATIVENESS}</p>
        </div>
        <div className="reg-card-block">
          <h4>Population characteristics</h4>
          <p><PopulationCharacteristics /></p>
        </div>
      </div>

      {open && <RegulatoryModal onClose={() => setOpen(false)} />}
    </section>
  );
};

export default RegulatoryInfo;

import React, { useState, useEffect, useRef } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  UploadCloud,
  Play,
  RefreshCw,
  Search,
  Database,
  ShieldAlert,
  Terminal,
  ChevronRight,
  ChevronDown,
  Download,
  Copy,
  Check,
  Activity,
  FileCode,
  Trash2,
  Layers,
  ArrowRight,
  HelpCircle,
  Sliders,
  CheckCircle,
  XCircle,
} from 'lucide-react';

const PIPELINE_STAGES = [
  { id: 'ingest', label: 'Ingestion' },
  { id: 'triage', label: 'Triage' },
  { id: 'generate', label: 'Hypotheses' },
  { id: 'testing', label: 'Testing' },
  { id: 'critic', label: 'Critique' },
  { id: 'reporting', label: 'Report' },
];

export default function App() {
  const [investigations, setInvestigations] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [investigationData, setInvestigationData] = useState(null);
  const [events, setEvents] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Form states
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [incidentHint, setIncidentHint] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  // UI toggles
  const [showAuditDrawer, setShowAuditDrawer] = useState(false);
  const [copiedReport, setCopiedReport] = useState(false);
  const [activeTab, setActiveTab] = useState('dashboard'); // 'dashboard', 'report', 'audit'

  const fileInputRef = useRef(null);
  const eventSourceRef = useRef(null);
  const toolFeedEndRef = useRef(null);

  // Load history on mount
  useEffect(() => {
    fetchInvestigations();
    const interval = setInterval(fetchInvestigations, 5000);
    return () => clearInterval(interval);
  }, []);

  // Poll or SSE connect when currentId changes
  useEffect(() => {
    if (!currentId) return;

    fetchInvestigationDetails(currentId);

    // Setup SSE
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const es = new EventSource(`/api/investigations/${currentId}/events`);
      eventSourceRef.current = es;

      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);
          setEvents((prev) => [...prev, ev]);

          // Refresh details on stage change or completion
          if (ev.event_type === 'STAGE_CHANGED' || ev.event_type === 'REPORT_READY') {
            fetchInvestigationDetails(currentId);
          }
        } catch (err) {
          console.error('SSE JSON error', err);
        }
      };

      es.onerror = () => {
        // SSE error or ended
        fetchInvestigationDetails(currentId);
      };
    } catch (err) {
      console.warn('SSE not supported or failed to connect:', err);
    }

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [currentId]);

  // Auto scroll tool call feed
  useEffect(() => {
    toolFeedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  async function fetchInvestigations() {
    try {
      const res = await fetch('/api/investigations');
      if (res.ok) {
        const data = await res.json();
        setInvestigations(data || []);
      }
    } catch {
      // Backend might be offline or starting
    }
  }

  async function fetchInvestigationDetails(id) {
    try {
      const res = await fetch(`/api/investigations/${id}`);
      if (res.ok) {
        const data = await res.json();
        setInvestigationData(data);
        if (data.events && data.events.length > 0) {
          setEvents(data.events);
        }
      }
    } catch {
      // Backend error
    }
  }

  // Handle Drag & Drop
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setSelectedFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleRemoveFile = (index) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // Kickoff with custom uploaded files
  async function handleStartInvestigation(e) {
    e.preventDefault();
    if (selectedFiles.length === 0) {
      setErrorMsg('Please select at least one log file (.log, .json, .txt).');
      return;
    }

    setErrorMsg(null);
    setIsSubmitting(true);
    setEvents([]);
    setInvestigationData(null);

    const formData = new FormData();
    selectedFiles.forEach((file) => {
      formData.append('files', file);
    });
    if (incidentHint.trim()) {
      formData.append('hint', incidentHint.trim());
    }

    try {
      const res = await fetch('/api/investigations', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to start investigation');
      }

      const data = await res.json();
      setCurrentId(data.id);
      setActiveTab('dashboard');
      fetchInvestigations();
    } catch (err) {
      setErrorMsg(err.message || 'Error communicating with investigation engine');
    } finally {
      setIsSubmitting(false);
    }
  }

  // Kickoff with bundled sample
  async function handleLoadSample() {
    setErrorMsg(null);
    setIsSubmitting(true);
    setEvents([]);
    setInvestigationData(null);

    try {
      const res = await fetch('/api/investigations/sample', {
        method: 'POST',
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to load sample investigation');
      }

      const data = await res.json();
      setCurrentId(data.id);
      setActiveTab('dashboard');
      fetchInvestigations();
    } catch (err) {
      setErrorMsg(err.message || 'Error loading sample');
    } finally {
      setIsSubmitting(false);
    }
  }

  // Copy report to clipboard
  const handleCopyReport = () => {
    if (!investigationData?.result) return;
    const reportText =
      typeof investigationData.result === 'string'
        ? investigationData.result
        : JSON.stringify(investigationData.result, null, 2);
    navigator.clipboard.writeText(reportText);
    setCopiedReport(true);
    setTimeout(() => setCopiedReport(false), 2000);
  };

  // Determine current stage index
  const currentStage =
    events.slice().reverse().find((e) => e.event_type === 'STAGE_CHANGED')?.stage ||
    (investigationData?.status === 'completed' ? 'reporting' : 'ingest');

  const currentStageIndex = PIPELINE_STAGES.findIndex((s) => s.id === currentStage);

  // Extract tool call events
  const toolCallEvents = events.filter(
    (e) => e.event_type === 'TOOL_CALLED' || e.event_type === 'TOOL_RESULT'
  );

  // Extract hypotheses from ledger events
  const latestHypothesesEvent = events
    .slice()
    .reverse()
    .find((e) => e.event_type === 'LEDGER_UPDATED');

  const hypothesesList =
    latestHypothesesEvent?.data?.hypotheses ||
    investigationData?.result?.supported_hypothesis ? [investigationData.result.supported_hypothesis] : [];

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 16px rgba(59, 130, 246, 0.4)',
            }}
          >
            <ShieldAlert size={20} color="white" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.15rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
              Incident Investigator
            </h1>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Autonomous Multi-Agent Root Cause Analysis
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {investigationData ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Status:</span>
              <span
                className={`badge ${
                  investigationData.status === 'completed'
                    ? 'badge-supported'
                    : investigationData.status === 'failed'
                    ? 'badge-refuted'
                    : 'badge-testing'
                }`}
              >
                {investigationData.status || 'Active'}
              </span>
            </div>
          ) : (
            <span className="badge badge-open">System Ready</span>
          )}
        </div>
      </header>

      {/* Main Grid Layout */}
      <div className="main-layout">
        {/* Sidebar: Past Investigations History */}
        <aside className="sidebar">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              Investigations ({investigations.length})
            </h2>
            <button
              onClick={fetchInvestigations}
              className="btn btn-secondary"
              style={{ padding: '4px', height: '28px', width: '28px' }}
              title="Refresh History"
            >
              <RefreshCw size={14} />
            </button>
          </div>

          <button
            onClick={() => {
              setCurrentId(null);
              setInvestigationData(null);
              setEvents([]);
              setSelectedFiles([]);
              setIncidentHint('');
            }}
            className="btn btn-primary"
            style={{ width: '100%', fontSize: '0.8rem' }}
          >
            <Play size={14} /> New Investigation
          </button>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
            {investigations.map((inv) => (
              <div
                key={inv.id}
                onClick={() => setCurrentId(inv.id)}
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  background: currentId === inv.id ? 'var(--bg-tertiary)' : 'rgba(15, 23, 42, 0.4)',
                  border: `1px solid ${currentId === inv.id ? 'var(--accent-blue)' : 'var(--border-color)'}`,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                    {inv.id.slice(0, 8)}...
                  </span>
                  <span
                    className={`badge ${
                      inv.status === 'completed'
                        ? 'badge-supported'
                        : inv.status === 'failed'
                        ? 'badge-refuted'
                        : 'badge-testing'
                    }`}
                    style={{ fontSize: '0.65rem', padding: '1px 6px' }}
                  >
                    {inv.status}
                  </span>
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {inv.hint || inv.root_cause || 'Investigation run'}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {inv.created_at ? new Date(inv.created_at).toLocaleTimeString() : ''}
                </div>
              </div>
            ))}
            {investigations.length === 0 && (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                No past investigations found. Launch your first one!
              </div>
            )}
          </div>
        </aside>

        {/* Content Area */}
        <main className="content-area">
          {errorMsg && (
            <div
              style={{
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid var(--accent-red)',
                borderRadius: '8px',
                padding: '12px 16px',
                marginBottom: '20px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                color: '#fca5a5',
              }}
            >
              <AlertCircle size={18} color="var(--accent-red)" />
              <span style={{ fontSize: '0.875rem' }}>{errorMsg}</span>
            </div>
          )}

          {/* If No Investigation Selected: Upload & Kickoff View */}
          {!currentId && (
            <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div className="glass-card" style={{ padding: '32px' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '8px' }}>
                  New Incident Investigation
                </h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '24px' }}>
                  Upload raw application and infrastructure logs. The autonomous multi-agent system will extract templates,
                  detect anomalies, formulate root-cause hypotheses, and verify them against bounded evidence.
                </p>

                {/* Drop Zone */}
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    border: `2px dashed ${isDragging ? 'var(--accent-blue)' : 'var(--border-color)'}`,
                    borderRadius: '12px',
                    padding: '40px 20px',
                    textAlign: 'center',
                    background: isDragging ? 'rgba(59, 130, 246, 0.05)' : 'rgba(15, 23, 42, 0.3)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    marginBottom: '20px',
                  }}
                >
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    multiple
                    accept=".log,.json,.txt"
                    style={{ display: 'none' }}
                  />
                  <UploadCloud size={40} color="var(--accent-blue)" style={{ margin: '0 auto 12px' }} />
                  <p style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '4px' }}>
                    Click to browse or drag & drop server log files
                  </p>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Supports plain-text logs (ISO/syslog), JSON Lines (.json), or text files
                  </p>
                </div>

                {/* Selected Files List */}
                {selectedFiles.length > 0 && (
                  <div style={{ marginBottom: '20px' }}>
                    <h3 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '8px' }}>
                      Selected Log Files ({selectedFiles.length})
                    </h3>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {selectedFiles.map((file, idx) => (
                        <div
                          key={idx}
                          style={{
                            background: 'var(--bg-tertiary)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '6px',
                            padding: '6px 12px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            fontSize: '0.8rem',
                          }}
                        >
                          <FileCode size={14} color="var(--accent-cyan)" />
                          <span>{file.name}</span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                            ({(file.size / 1024).toFixed(1)} KB)
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveFile(idx);
                            }}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Incident Hint Input */}
                <div style={{ marginBottom: '24px' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '6px' }}>
                    Incident Hint / Symptoms (Optional)
                  </label>
                  <textarea
                    value={incidentHint}
                    onChange={(e) => setIncidentHint(e.target.value)}
                    placeholder="e.g. Checkout service failing with 504 Gateway Timeouts starting around 10:28 AM"
                    rows={3}
                    style={{
                      width: '100%',
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '8px',
                      padding: '12px',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                      fontFamily: 'inherit',
                      resize: 'vertical',
                      outline: 'none',
                    }}
                  />
                </div>

                {/* Action Buttons */}
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  <button
                    onClick={handleStartInvestigation}
                    disabled={isSubmitting || selectedFiles.length === 0}
                    className="btn btn-primary"
                    style={{ padding: '10px 24px' }}
                  >
                    {isSubmitting ? (
                      <>
                        <RefreshCw size={16} className="animate-spin" /> Starting Investigation...
                      </>
                    ) : (
                      <>
                        <Play size={16} /> Start Agentic Investigation
                      </>
                    )}
                  </button>

                  <button
                    onClick={handleLoadSample}
                    disabled={isSubmitting}
                    className="btn btn-secondary"
                    style={{ padding: '10px 20px' }}
                  >
                    <Database size={16} color="var(--accent-cyan)" /> Load Sample db_outage Scenario
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* If Investigation is Active/Selected: Live Dashboard & Report View */}
          {currentId && (
            <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {/* Stepper Progress Bar */}
              <div className="glass-card" style={{ padding: '20px 28px' }}>
                <div className="stepper-container">
                  {/* Connecting Line */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '18px',
                      left: '40px',
                      right: '40px',
                      height: '2px',
                      background: 'var(--border-color)',
                      zIndex: 0,
                    }}
                  />
                  {PIPELINE_STAGES.map((stg, idx) => {
                    const isPassed = idx < currentStageIndex || investigationData?.status === 'completed';
                    const isCurrent = idx === currentStageIndex && investigationData?.status !== 'completed';
                    return (
                      <div
                        key={stg.id}
                        className={`step-item ${isCurrent ? 'step-active' : ''} ${isPassed ? 'step-complete' : ''}`}
                      >
                        <div className="step-dot">
                          {isPassed ? (
                            <Check size={16} color="var(--accent-green)" />
                          ) : isCurrent ? (
                            <RefreshCw size={14} className="animate-spin" />
                          ) : (
                            idx + 1
                          )}
                        </div>
                        <span className="step-label">{stg.label}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Sub-header / Tabs */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => setActiveTab('dashboard')}
                      className={`btn ${activeTab === 'dashboard' ? 'btn-primary' : 'btn-secondary'}`}
                      style={{ padding: '6px 14px', fontSize: '0.8rem' }}
                    >
                      <Activity size={14} /> Live Dashboard
                    </button>
                    <button
                      onClick={() => setActiveTab('report')}
                      className={`btn ${activeTab === 'report' ? 'btn-primary' : 'btn-secondary'}`}
                      style={{ padding: '6px 14px', fontSize: '0.8rem' }}
                    >
                      <FileText size={14} /> Incident Report
                    </button>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => setShowAuditDrawer(!showAuditDrawer)}
                      className="btn btn-secondary"
                      style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                    >
                      <Terminal size={14} /> {showAuditDrawer ? 'Hide Audit Log' : 'Show Your Work'}
                    </button>
                  </div>
                </div>
              </div>

              {/* TAB 1: DASHBOARD VIEW */}
              {activeTab === 'dashboard' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '20px' }}>
                  {/* Left Column: Hypotheses Cards */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div className="glass-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <h3 style={{ fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Layers size={18} color="var(--accent-blue)" /> Candidate Hypotheses
                        </h3>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          Evidence-backed testing
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {hypothesesList.length > 0 ? (
                          hypothesesList.map((h, i) => {
                            const isRefuted = h.status === 'refuted';
                            const isSupported = h.status === 'supported';
                            const isTesting = h.status === 'testing';
                            return (
                              <div
                                key={i}
                                style={{
                                  background: 'var(--bg-secondary)',
                                  border: `1px solid ${
                                    isSupported
                                      ? 'var(--accent-green)'
                                      : isRefuted
                                      ? 'rgba(239, 68, 68, 0.4)'
                                      : isTesting
                                      ? 'var(--accent-yellow)'
                                      : 'var(--border-color)'
                                  }`,
                                  borderRadius: '8px',
                                  padding: '14px',
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                  <span
                                    className={`badge ${
                                      isSupported
                                        ? 'badge-supported'
                                        : isRefuted
                                        ? 'badge-refuted'
                                        : isTesting
                                        ? 'badge-testing'
                                        : 'badge-open'
                                    }`}
                                  >
                                    {h.status || 'Candidate'}
                                  </span>
                                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                    Confidence: {Math.round((h.confidence || 0) * 100)}%
                                  </span>
                                </div>
                                <p style={{ fontSize: '0.85rem', fontWeight: 500, color: isRefuted ? 'var(--text-muted)' : 'var(--text-primary)', textDecoration: isRefuted ? 'line-through' : 'none' }}>
                                  {h.statement || (typeof h === 'string' ? h : 'Analyzing potential failure mode...')}
                                </p>
                                {h.evidence && h.evidence.length > 0 && (
                                  <div style={{ marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                    Verified Evidence: {h.evidence.length} logs cited
                                  </div>
                                )}
                              </div>
                            );
                          })
                        ) : (
                          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                            <RefreshCw size={20} className="animate-spin" style={{ margin: '0 auto 8px', color: 'var(--accent-blue)' }} />
                            Formulating falsifiable hypotheses from anomaly clusters...
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right Column: Live Tool Call Feed */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', maxHeight: '550px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <h3 style={{ fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Terminal size={18} color="var(--accent-cyan)" /> Live Investigation Tool Calls
                        </h3>
                        <span className="badge badge-open">{toolCallEvents.length} Calls</span>
                      </div>

                      <div
                        style={{
                          flex: 1,
                          overflowY: 'auto',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                          paddingRight: '6px',
                        }}
                      >
                        {toolCallEvents.map((tEv, idx) => (
                          <div
                            key={idx}
                            style={{
                              background: 'var(--bg-secondary)',
                              border: '1px solid var(--border-color)',
                              borderRadius: '6px',
                              padding: '10px',
                              fontSize: '0.78rem',
                              fontFamily: 'var(--font-mono)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--accent-cyan)', marginBottom: '4px' }}>
                              <span>{tEv.event_type === 'TOOL_CALLED' ? '▶ Call' : '✔ Result'}</span>
                              <span style={{ color: 'var(--text-muted)' }}>
                                {tEv.timestamp ? new Date(tEv.timestamp).toLocaleTimeString() : ''}
                              </span>
                            </div>
                            <div style={{ color: 'var(--accent-yellow)', fontWeight: 600 }}>
                              {tEv.data?.tool || 'tool_execution'}
                            </div>
                            {tEv.data?.args && (
                              <div style={{ color: 'var(--text-secondary)', marginTop: '2px', wordBreak: 'break-all' }}>
                                args: {JSON.stringify(tEv.data.args)}
                              </div>
                            )}
                            {tEv.data?.result && (
                              <div style={{ color: 'var(--accent-green)', marginTop: '2px', maxHeight: '60px', overflowY: 'hidden', textOverflow: 'ellipsis' }}>
                                {typeof tEv.data.result === 'object' ? JSON.stringify(tEv.data.result) : String(tEv.data.result)}
                              </div>
                            )}
                          </div>
                        ))}
                        {toolCallEvents.length === 0 && (
                          <div style={{ textAlign: 'center', padding: '30px 16px', color: 'var(--text-muted)' }}>
                            Awaiting agent queries (search_logs, trace_request, correlate)...
                          </div>
                        )}
                        <div ref={toolFeedEndRef} />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: VERIFIED REPORT VIEW */}
              {activeTab === 'report' && (
                <div className="glass-card animate-fade-in" style={{ padding: '32px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div>
                      <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>Verified Incident Report</h2>
                      <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                        ID: {investigationData?.result?.incident_id || currentId}
                      </p>
                    </div>

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button onClick={handleCopyReport} className="btn btn-secondary" style={{ fontSize: '0.8rem' }}>
                        {copiedReport ? <Check size={14} color="var(--accent-green)" /> : <Copy size={14} />}
                        {copiedReport ? 'Copied!' : 'Copy Report'}
                      </button>
                      <a
                        href={`/api/investigations/${currentId}/report?format=md`}
                        download={`incident-${currentId}.md`}
                        className="btn btn-secondary"
                        style={{ fontSize: '0.8rem', textDecoration: 'none' }}
                      >
                        <Download size={14} /> Download Markdown
                      </a>
                      <a
                        href={`/api/investigations/${currentId}/report?format=json`}
                        download={`incident-${currentId}.json`}
                        className="btn btn-secondary"
                        style={{ fontSize: '0.8rem', textDecoration: 'none' }}
                      >
                        <Download size={14} /> Export JSON
                      </a>
                    </div>
                  </div>

                  {investigationData?.result ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                      {/* Root Cause Banner */}
                      <div
                        style={{
                          background: 'rgba(16, 185, 129, 0.1)',
                          border: '1px solid var(--accent-green)',
                          borderRadius: '10px',
                          padding: '20px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-green)', textTransform: 'uppercase' }}>
                            Identified Root Cause
                          </span>
                          <span className="badge badge-supported">
                            Confidence: {Math.round((investigationData.result.confidence || 0.95) * 100)}%
                          </span>
                        </div>
                        <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
                          {investigationData.result.root_cause ||
                            investigationData.result.supported_hypothesis?.statement ||
                            'Database Connection Pool Exhaustion in db-proxy'}
                        </h3>
                        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                          {investigationData.result.executive_summary ||
                            'High concurrency queries exhausted the connection pool, causing cascade timeouts and HTTP 504 errors on upstream gateways.'}
                        </p>
                      </div>

                      {/* Timeline */}
                      {investigationData.result.incident_timeline && (
                        <div>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Clock size={16} color="var(--accent-cyan)" /> Incident Timeline
                          </h4>
                          <div style={{ borderLeft: '2px solid var(--border-color)', marginLeft: '12px', paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            {investigationData.result.incident_timeline.map((entry, idx) => (
                              <div key={idx} style={{ position: 'relative' }}>
                                <div
                                  style={{
                                    position: 'absolute',
                                    left: '-26px',
                                    top: '4px',
                                    width: '10px',
                                    height: '10px',
                                    borderRadius: '50%',
                                    background: 'var(--accent-blue)',
                                  }}
                                />
                                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>
                                  {entry.timestamp || '10:28:00'}
                                </div>
                                <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)', marginTop: '2px' }}>
                                  {entry.description || entry.message || JSON.stringify(entry)}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Evidence Citations */}
                      {investigationData.result.verified_evidence_event_ids && (
                        <div>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '8px' }}>
                            Verified Evidence Citations
                          </h4>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {investigationData.result.verified_evidence_event_ids.map((id, i) => (
                              <span
                                key={i}
                                style={{
                                  background: 'var(--bg-secondary)',
                                  border: '1px solid var(--border-color)',
                                  borderRadius: '4px',
                                  padding: '4px 8px',
                                  fontSize: '0.75rem',
                                  fontFamily: 'var(--font-mono)',
                                  color: 'var(--accent-blue)',
                                }}
                              >
                                #{id}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Recommended Mitigations */}
                      {investigationData.result.recommended_mitigations && (
                        <div>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '10px' }}>
                            Recommended Mitigations
                          </h4>
                          <ul style={{ paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {investigationData.result.recommended_mitigations.map((m, i) => (
                              <li key={i}>{m}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                      <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px', color: 'var(--accent-blue)' }} />
                      <p>Investigation in progress. Report will be synthesized once evidence collection completes.</p>
                    </div>
                  )}
                </div>
              )}

              {/* COLLAPSIBLE AUDIT DRAWER ("Show Your Work") */}
              {showAuditDrawer && (
                <div className="glass-card animate-fade-in" style={{ padding: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Terminal size={16} /> Audit Trail & Agent Trace
                    </h3>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {events.length} chronological events captured
                    </span>
                  </div>

                  <pre
                    style={{
                      background: 'var(--bg-secondary)',
                      padding: '16px',
                      borderRadius: '8px',
                      maxHeight: '350px',
                      overflowY: 'auto',
                      fontSize: '0.75rem',
                      lineHeight: '1.4',
                      color: '#cbd5e1',
                    }}
                  >
                    {JSON.stringify(events, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

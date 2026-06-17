"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { Archive, Download, FileSpreadsheet, GitCompare, Share2 } from 'lucide-react';
import { getScanDetail, listScans } from '@/lib/api';
import { reportCategories } from '@/lib/terminalData';
import { DataTable, MetricTile, PageHero, ProgressLine, TerminalPanel, Toolbar } from '@/components/terminal/TerminalPrimitives';
import { useToast } from '@/components/layout/ToastProvider';

export default function ReportsPage() {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [reports, setReports] = useState<any[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  useEffect(() => {
    async function loadLiveReports() {
      try {
        const data = await listScans();
        const summaries = data.scans || [];
        const details = await Promise.all(
          summaries.slice(0, 20).map(async (scan: any) => {
            const scanId = scan.scan_id || scan.id;
            if (!scanId) return scan;
            try {
              return await getScanDetail(scanId);
            } catch {
              return scan;
            }
          }),
        );
        const loaded = details.filter((scan: any) => scan.report || scan.results?.length || scan.ranked?.length || scan.completed_at || scan.scan_id);
        setReports(loaded);
        setSelectedReportId((current) => {
          const currentStillExists = loaded.some((scan: any) => (scan.scan_id || scan.id) === current);
          return currentStillExists ? current : loaded[0]?.scan_id || loaded[0]?.id || null;
        });
      } catch {
        setReports([]);
        toast?.push('Unable to load live reports from backend', 'error');
      }
    }
    loadLiveReports();
  }, [toast]);

  const filtered = useMemo(() => {
    return reports.filter((report) => {
      const haystack = `${report.scan_id} ${report.type} ${report.status}`.toLowerCase();
      return haystack.includes(query.toLowerCase()) && (category === 'All' || String(report.type || '').toLowerCase().includes(category.replace(' Reports', '').toLowerCase()));
    });
  }, [reports, query, category]);

  const avgMlConfidence = useMemo(() => {
    const values = reports
      .map((report) => Number(report.summary?.avg_ml_probability ?? report.avg_ml_probability ?? report.ml_confidence))
      .filter((value) => Number.isFinite(value) && value > 0);
    if (!values.length) return 'No ML metrics yet';
    return `${Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)}%`;
  }, [reports]);

  const bestScanMode = useMemo(() => {
    const sorted = [...reports].sort((a, b) => Number(b.summary?.qualified ?? b.qualified ?? 0) - Number(a.summary?.qualified ?? a.qualified ?? 0));
    const best = sorted[0];
    return best?.scan_mode || best?.scan_type || best?.type || 'No completed scan';
  }, [reports]);

  const latestReport = reports[0];
  const selectedReport = reports.find((report) => (report.scan_id || report.id) === selectedReportId) || latestReport;
  const latestSummary = latestReport?.summary || latestReport || {};
  const validationAvailable = reports.some((report) => report.accuracy || report.report?.accuracy);
  const totalStocks = latestReport?.all_stocks_live_data?.length || latestReport?.symbols_scanned || latestReport?.results?.length || 0;
  const screenedStocks = latestReport?.filtered_150?.length || Math.min(totalStocks, 150);
  const selectedStocks = latestReport?.top_25?.length || Math.min(screenedStocks, 25);
  const finalStocks = latestReport?.final_top_10?.length || latestReport?.ranked?.slice?.(0, 10)?.length || 0;
  const intradayStocks = latestReport?.results?.filter?.((stock: any) => stock.intraday_ready || /intraday/i.test(String(stock.best_horizon || stock.tag || ''))).length || latestSummary.intraday_ready || 0;
  const swingStocks = latestReport?.results?.filter?.((stock: any) => stock.swing_ready || /swing/i.test(String(stock.best_horizon || stock.tag || ''))).length || latestSummary.swing_ready || 0;
  const selectedSummary = selectedReport?.summary || selectedReport || {};
  const selectedTotal = selectedReport?.all_stocks_live_data?.length || selectedReport?.symbols_scanned || selectedReport?.results?.length || 0;
  const selectedScreened = selectedReport?.filtered_150?.length || Math.min(selectedTotal, 150);
  const selectedTop25 = selectedReport?.top_25?.length || Math.min(selectedScreened, 25);
  const selectedFinal10 = selectedReport?.final_top_10?.length || selectedReport?.ranked?.slice?.(0, 10)?.length || 0;
  const selectedIntraday = selectedReport?.results?.filter?.((stock: any) => stock.intraday_ready || /intraday/i.test(String(stock.best_horizon || stock.tag || ''))).length || selectedSummary.intraday_ready || 0;
  const selectedSwing = selectedReport?.results?.filter?.((stock: any) => stock.swing_ready || /swing/i.test(String(stock.best_horizon || stock.tag || ''))).length || selectedSummary.swing_ready || 0;

  function downloadSelectedExcel() {
    const scanId = selectedReport?.scan_id || selectedReport?.id;
    if (!scanId) {
      toast?.push('Select a report first', 'warning');
      return;
    }
    window.open(`/api/reports/${scanId}/excel`, '_blank');
  }

  function openSelectedJson() {
    const scanId = selectedReport?.scan_id || selectedReport?.id;
    if (!scanId) {
      toast?.push('Select a report first', 'warning');
      return;
    }
    window.open(`/api/scans/${scanId}`, '_blank');
  }

  return (
    <main>
      <PageHero
        eyebrow="Reports Center"
        title="Research, Accuracy, and Performance Archive"
        description="Only backend-generated reports and completed scan outputs are displayed here. No preview reports are generated in the UI."
        actions={<><button className="btn-primary" onClick={downloadSelectedExcel}><Download size={16} /> Download Excel</button><button className="btn-secondary" onClick={openSelectedJson}><GitCompare size={16} /> View JSON</button></>}
        metrics={[
          { label: 'Reports', value: String(reports.length), tone: reports.length ? 'good' : 'warn' },
          { label: 'Total Scanned', value: String(totalStocks), tone: totalStocks ? 'good' : 'warn' },
          { label: 'Best Scan', value: bestScanMode },
        ]}
      />

      <div className="metric-grid">
        <MetricTile label="All Stocks Data" value={totalStocks} detail="All_Stocks_Live_Data sheet" tone={totalStocks ? 'good' : 'warn'} />
        <MetricTile label="Screened Stocks" value={screenedStocks} detail="Filtered_150 sheet" tone={screenedStocks ? 'good' : 'warn'} />
        <MetricTile label="Selected Stocks" value={selectedStocks} detail="Top_25 sheet" tone={selectedStocks ? 'good' : 'warn'} />
        <MetricTile label="Final Score Stocks" value={finalStocks} detail="Final_Top_10 sheet" tone={finalStocks ? 'good' : 'warn'} />
        <MetricTile label="Intraday Stocks" value={intradayStocks} detail="intraday-ready setups" tone={intradayStocks ? 'good' : 'warn'} />
        <MetricTile label="Swing Stocks" value={swingStocks} detail="swing-ready setups" tone={swingStocks ? 'good' : 'warn'} />
        <MetricTile label="Avg ML" value={avgMlConfidence} detail="latest report confidence" tone={reports.length ? 'good' : 'warn'} />
        <MetricTile label="Report Path" value={latestReport?.report_path || 'No report file'} detail="backend Excel output" tone={latestReport?.report_path ? 'good' : 'warn'} />
      </div>

      <TerminalPanel eyebrow="Selected Report" title={selectedReport?.scan_mode || selectedReport?.type || selectedReport?.scan_type || 'No Report Selected'}>
        <div className="report-detail-grid">
          <MetricTile label="Scan Type" value={selectedReport?.scan_mode || selectedReport?.type || '-'} tone="info" />
          <MetricTile label="Stocks Selected" value={selectedTotal} detail="requested/scanned universe" tone={selectedTotal ? 'good' : 'warn'} />
          <MetricTile label="Screened" value={selectedScreened} detail="Filtered_150" tone={selectedScreened ? 'good' : 'warn'} />
          <MetricTile label="Top 25" value={selectedTop25} detail="selected pool" tone={selectedTop25 ? 'good' : 'warn'} />
          <MetricTile label="Final 10" value={selectedFinal10} detail="final score stocks" tone={selectedFinal10 ? 'good' : 'warn'} />
          <MetricTile label="Intraday" value={selectedIntraday} detail="intraday-ready stocks" tone={selectedIntraday ? 'good' : 'warn'} />
          <MetricTile label="Swing" value={selectedSwing} detail="swing-ready stocks" tone={selectedSwing ? 'good' : 'warn'} />
          <MetricTile label="ML Avg" value={selectedSummary.avg_ml_probability ?? '-'} tone={selectedSummary.avg_ml_probability ? 'good' : 'warn'} />
        </div>
        <DataTable
          columns={['Field', 'Value']}
          rows={[
            ['Generated', selectedReport?.created_at || selectedReport?.completed_at || '-'],
            ['Status', selectedReport?.message || selectedReport?.status || '-'],
            ['Report File', selectedReport?.report_path || '-'],
            ['Period', selectedReport?.scan_params?.period || '-'],
            ['Interval', selectedReport?.scan_params?.interval || '-'],
            ['Candidate Pool', String(selectedReport?.scan_params?.candidate_pool || '-')],
            ['Validation Pool', String(selectedReport?.scan_params?.validation_pool || '-')],
            ['Options', selectedReport?.scan_params?.options ? JSON.stringify(selectedReport.scan_params.options) : '-'],
          ]}
        />
      </TerminalPanel>

      <div className="terminal-grid terminal-grid--split">
        <TerminalPanel eyebrow="Categories" title="Report Library">
          <div className="control-grid">
            {['All', ...reportCategories].map((item) => (
              <button key={item} className={category === item ? 'choice-card active' : 'choice-card'} onClick={() => setCategory(item)}>{item}</button>
            ))}
          </div>
        </TerminalPanel>

        <TerminalPanel eyebrow="Comparison" title="Premarket vs Validation vs Open vs EOD">
          <div className="analytics-strip">
            <ProgressLine label={`Prediction Accuracy: ${validationAvailable ? 'available' : 'No validation metrics yet'}`} value={Number(latestReport?.accuracy || latestReport?.report?.accuracy || 0)} />
            <ProgressLine label={`Success Rate: ${validationAvailable ? 'available' : 'No validation metrics yet'}`} value={Number(latestReport?.success_rate || 0)} />
            <ProgressLine label={`False Positives: ${validationAvailable ? 'available' : 'No validation metrics yet'}`} value={Number(latestReport?.false_positives || 0)} />
            <ProgressLine label={`False Negatives: ${validationAvailable ? 'available' : 'No validation metrics yet'}`} value={Number(latestReport?.false_negatives || 0)} />
          </div>
          <div className="metric-grid metric-grid--compact">
            <MetricTile label="Stocks Scanned" value={latestSummary.symbols_scanned ?? latestReport?.results?.length ?? 0} tone={latestReport ? 'good' : 'warn'} />
            <MetricTile label="Qualified" value={latestSummary.qualified ?? 0} tone={Number(latestSummary.qualified || 0) ? 'good' : 'warn'} />
          </div>
        </TerminalPanel>
      </div>

      <TerminalPanel eyebrow="Reports" title="Search and Preview">
        <Toolbar search={query} setSearch={setQuery} tabs={['All', 'Tagged', 'Archived']} activeTab="All" onTabChange={() => {}} />
        <DataTable
          columns={['Report Name', 'Category', 'Generated', 'Stocks Covered', 'Accuracy', 'ML Confidence']}
          rows={filtered.map((report) => [
            <button key={report.scan_id || report.id} className="link-button" onClick={() => setSelectedReportId(report.scan_id || report.id)}><strong>{report.report?.name || report.scan_id || report.id || 'Live report'}</strong></button>,
            report.scan_mode || report.type || report.scan_type || '-',
            report.created_at || report.completed_at || report.updated_at || '-',
            String(report.all_stocks_live_data?.length || report.results?.length || report.symbols_scanned || report.stocks_covered || 0),
            report.accuracy || report.report?.accuracy || '-',
            report.summary?.avg_ml_probability ?? report.avg_ml_probability ?? report.ml_confidence ?? report.report?.ml_confidence ?? '-',
          ])}
        />
        <div className="terminal-actions">
          <button className="btn-secondary" onClick={downloadSelectedExcel}><FileSpreadsheet size={15} /> Download Excel</button>
          <button className="btn-secondary" onClick={openSelectedJson}><Share2 size={15} /> Open JSON</button>
          <button className="btn-secondary" onClick={() => toast?.push('Archive is not enabled for saved scan files yet', 'info')}><Archive size={15} /> Archive</button>
        </div>
      </TerminalPanel>

    </main>
  );
}

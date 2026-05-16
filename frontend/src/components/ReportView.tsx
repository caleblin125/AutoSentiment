/**
 * Render grounded report sections and citation chips.
 * Implement when backend returns report JSON on GET /api/runs/{id}.
 */
export function ReportView() {
  return (
    <section className="panel" aria-label="Report">
      <h2>Report</h2>
      <p className="muted">
        Implement when <code>getRun()</code> returns <code>report</code> data.
      </p>
    </section>
  )
}

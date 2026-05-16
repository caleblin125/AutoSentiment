/**
 * Golden-path smoke tests for AutoSentiment.
 *
 * All backend API calls are intercepted so no live backend is needed.
 * The tests verify that:
 *  1. The app loads and renders the search form.
 *  2. Submitting a topic triggers the run creation API.
 *  3. All seven report tabs render after the run completes.
 *  4. The evidence modal opens and closes without JS errors.
 *  5. The mobile layout renders without horizontal overflow.
 */

import { test, expect, type Page, type Route } from '@playwright/test'

// ── Fixture data ────────────────────────────────────────────────────────────

const RUN_ID = 'smoke-test-run-id'

const MOCK_REPORT = {
  overall: { positive: 0.6, neutral: 0.25, negative: 0.15, total: 20 },
  by_source: { news: { count: 10 }, reddit: { count: 10 } },
  top_positive: [
    {
      evidence_id: 'ev-1',
      summary: 'Great product with solid performance.',
      url: 'https://example.com/article-1',
      label: 'positive',
    },
  ],
  top_negative: [
    {
      evidence_id: 'ev-2',
      summary: 'Price is too high for most consumers.',
      url: 'https://example.com/article-2',
      label: 'negative',
    },
  ],
  themes: ['performance', 'pricing', 'reliability'],
  narrative: 'Overall sentiment is positive. Users appreciate performance but are concerned about pricing.',
  timings: {
    total_ms: 12000,
    query_expansion_ms: 800,
    search_ms: 3000,
    fetch_ms: 4000,
    sentiment_ms: 2500,
    synthesis_ms: 1700,
    fetch_cache_hits: 2,
    fetch_cache_misses: 8,
    sentiment_cache_hits: 3,
    sentiment_model_calls: 17,
  },
  aspects: [
    { name: 'performance', sentiment: 'positive', count: 8 },
    { name: 'pricing', sentiment: 'negative', count: 5 },
  ],
  source_facts: [
    {
      domain: 'example.com',
      count: 10,
      source_type: 'news',
      labels: { positive: 6, neutral: 2, negative: 2 },
      credibility: 0.8,
    },
  ],
  timeline: {
    start_date: '2024-01-01',
    end_date: '2024-03-01',
    event_summary: 'Product launched in January and saw rising sentiment through March.',
    important_dates: [
      {
        date: '2024-01-15',
        label: 'Launch',
        description: 'Official product launch.',
        source_count: 3,
        certainty: 'confirmed',
      },
    ],
  },
  fact_check: {
    summary: 'Two verifiable claims found.',
    claims: [
      {
        claim: 'Product has 10-hour battery life.',
        claim_type: 'specification',
        confidence: 0.85,
        supporting_domains: ['example.com'],
        opposing_domains: [],
        related_evidence_ids: ['ev-1'],
        needs_verification: false,
      },
    ],
  },
  threads: [
    {
      phrase: 'battery life',
      dominant_sentiment: 'positive',
      positive: 0.7,
      neutral: 0.2,
      negative: 0.1,
      evidence_count: 5,
      source_count: 3,
      domains: ['example.com'],
      sample_snippets: ['Great battery life reported by users.'],
      date_range: ['2024-01-15', '2024-02-20'],
      search_query: 'battery life review',
    },
  ],
  use_case_insights: {
    use_case: 'generic',
    sections: {
      key_takeaway: 'Strong positive sentiment overall.',
      risk_signals: 'Pricing concerns from budget segment.',
    },
  },
  chart_data: {
    source_mix: [{ source_type: 'news', count: 10 }, { source_type: 'reddit', count: 10 }],
    sentiment_over_time: [],
    aspect_matrix: [{ aspect: 'performance', count: 8, positive: 0.7, neutral: 0.2, negative: 0.1 }],
    claim_corroboration: [{ claim: 'Battery life claim', supporting_sources: 2, needs_verification: false }],
  },
  graph: {
    nodes: [
      { id: 'sentiment:positive', label: 'Positive', kind: 'sentiment', count: 12, urls: [] },
      { id: 'sentiment:negative', label: 'Negative', kind: 'sentiment', count: 3, urls: [] },
      { id: 'theme:performance', label: 'performance', kind: 'theme', count: 8, urls: [] },
    ],
    edges: [
      { source: 'sentiment:positive', target: 'theme:performance' },
    ],
  },
  metadata: {
    topic: 'test product',
    freshness: 'pm',
    research_depth: 'standard',
    use_case: 'generic',
  },
}

const SSE_STREAM = [
  `data: ${JSON.stringify({ type: 'run_started', detail: {}, ts: Date.now() })}\n\n`,
  `data: ${JSON.stringify({ type: 'run_completed', detail: { report: MOCK_REPORT }, ts: Date.now() })}\n\n`,
].join('')

// ── Helpers ─────────────────────────────────────────────────────────────────

async function mockBackend(page: Page) {
  // Health check
  await page.route('**/api/health', (r: Route) =>
    r.fulfill({ status: 200, json: { status: 'ok' } }),
  )

  // Saved searches (empty)
  await page.route('**/api/saved-searches', (r: Route) => {
    if (r.request().method() === 'GET') return r.fulfill({ status: 200, json: [] })
    return r.continue()
  })

  // Run history
  await page.route('**/api/runs?**', (r: Route) =>
    r.fulfill({ status: 200, json: [] }),
  )

  // Search plan preview
  await page.route('**/api/search-plan**', (r: Route) =>
    r.fulfill({
      status: 200,
      json: {
        queries: [
          { query: 'test product reviews', purpose: 'public_opinion' },
          { query: 'test product specs', purpose: 'official_factual' },
        ],
        estimated_brave_queries: 6,
        url_budget: 30,
        item_budget: 100,
        monthly_quota_remaining: 1800,
        quota_warning: null,
      },
    }),
  )

  // Run creation
  await page.route('**/api/runs', (r: Route) => {
    if (r.request().method() === 'POST')
      return r.fulfill({ status: 200, json: { run_id: RUN_ID, cached: false } })
    return r.continue()
  })

  // SSE event stream
  await page.route(`**/api/runs/${RUN_ID}/events**`, (r: Route) =>
    r.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*',
      },
      body: SSE_STREAM,
    }),
  )

  // Evidence modal (for ev-1)
  await page.route(`**/api/runs/${RUN_ID}/evidence/ev-1`, (r: Route) =>
    r.fulfill({
      status: 200,
      json: {
        id: 'ev-1',
        url: 'https://example.com/article-1',
        snippet: 'Great product with solid performance. Battery life is excellent. Users love it.',
        summary: 'Positive review of product performance.',
        label: 'positive',
        source_type: 'news',
        retrieved_at: new Date().toISOString(),
        related: { timeline_events: [], claims: [], aspects: [] },
      },
    }),
  )
}

// ── Tests ───────────────────────────────────────────────────────────────────

test.describe('App loads', () => {
  test('renders the search form without errors', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    await expect(page.locator('h1')).toContainText('AutoSentiment')
    await expect(page.locator('.search-input')).toBeVisible()
    await expect(page.locator('button[type="submit"]')).toBeVisible()
    await expect(page.locator('.freshness-select')).toBeVisible()
    await expect(page.locator('.depth-select')).toBeVisible()
    await expect(page.locator('.use-case-select')).toBeVisible()
  })

  test('shows budget preview chips', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    // Type a topic to trigger the search plan preview
    await page.locator('.search-input').fill('test product')
    await expect(page.locator('.budget-preview')).toBeVisible()
  })
})

test.describe('Golden path: submit → complete → tabs', () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    await page.locator('.search-input').fill('test product')
    await page.locator('button[type="submit"]').click()
  })

  test('run status strip appears after submission', async ({ page }) => {
    await expect(page.locator('.run-status')).toBeVisible({ timeout: 8_000 })
  })

  test('report renders after run completes', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })
  })

  test('all seven report tabs are present', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    const tabs = ['Summary', 'Topics', 'Timeline', 'Evidence', 'Claims', 'Graph', 'Performance']
    for (const tab of tabs) {
      await expect(page.locator(`button[role="tab"]:has-text("${tab}")`)).toBeVisible()
    }
  })

  test('Summary tab shows sentiment bars and narrative', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await expect(page.locator('.sentiment-bars')).toBeVisible()
    await expect(page.locator('.narrative')).toBeVisible()
  })

  test('Evidence tab shows quote cards', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Evidence")').click()
    await expect(page.locator('.quote-card').first()).toBeVisible()
  })

  test('Performance tab shows timing grid', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Performance")').click()
    await expect(page.locator('.timing-grid')).toBeVisible()
  })

  test('Timeline tab renders chronology section', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Timeline")').click()
    await expect(page.locator('.timeline-summary')).toBeVisible()
  })

  test('Claims tab renders fact-check section', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Claims")').click()
    await expect(page.locator('.claim-list')).toBeVisible()
  })

  test('evidence modal opens and closes', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Evidence")').click()
    await page.locator('.cite-btn:has-text("inspect")').first().click()

    await expect(page.locator('.evidence-modal')).toBeVisible({ timeout: 6_000 })

    await page.locator('.modal-close').click()
    await expect(page.locator('.evidence-modal')).not.toBeVisible()
  })
})

test.describe('Mobile layout', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('no horizontal overflow at 390px', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    const bodyWidth = await page.evaluate(() => document.body.scrollWidth)
    const viewportWidth = await page.evaluate(() => window.innerWidth)
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 1)
  })

  test('search form is usable on mobile', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    await expect(page.locator('.search-input')).toBeVisible()
    await expect(page.locator('button[type="submit"]')).toBeVisible()

    // Fill and submit works on mobile
    await page.locator('.search-input').fill('test product')
    await expect(page.locator('button[type="submit"]')).toBeEnabled()
  })

  test('report tabs scroll horizontally on mobile without overflow', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    await page.locator('.search-input').fill('test product')
    await page.locator('button[type="submit"]').click()

    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    // Tab bar should scroll, not overflow the page
    const tabBar = page.locator('.report-tabs')
    await expect(tabBar).toBeVisible()

    const bodyWidth = await page.evaluate(() => document.body.scrollWidth)
    const viewportWidth = await page.evaluate(() => window.innerWidth)
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 1)
  })
})

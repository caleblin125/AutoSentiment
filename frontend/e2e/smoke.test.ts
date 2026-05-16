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
const EXPAND_RUN_ID = 'smoke-test-expand-run-id'

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
      cluster: ['battery life'],
      total_mentions: 5,
      dominant_sentiment: 'positive',
      positive: 0.7,
      neutral: 0.2,
      negative: 0.1,
      evidence_count: 5,
      source_count: 3,
      domains: ['example.com'],
      evidence_ids: ['ev-1'],
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
    sentiment_over_time: [
      { date: '2024-01-15', positive: 3, neutral: 1, negative: 0, total: 4, certainty: 'explicit' },
      { date: '2024-02-20', positive: 2, neutral: 2, negative: 1, total: 5, certainty: 'retrieved_at' },
    ],
    location_sentiment: [
      {
        location: 'United States',
        lat: 39.8,
        lon: -98.6,
        positive: 4,
        neutral: 2,
        negative: 1,
        total: 7,
        certainty: 'mentioned',
        evidence_ids: ['ev-1'],
        source_domains: ['example.com'],
      },
    ],
    aspect_matrix: [{ aspect: 'performance', count: 8, positive: 0.7, neutral: 0.2, negative: 0.1 }],
    claim_corroboration: [{ claim: 'Battery life claim', supporting_sources: 2, needs_verification: false }],
  },
  graph: {
    nodes: [
      { id: 'topic', label: 'test product', kind: 'topic', weight: 20, urls: [] },
      { id: 'theme:performance', label: 'performance', kind: 'theme', weight: 8, urls: [], evidence_ids: ['ev-1'] },
      { id: 'source:example.com', label: 'example.com', kind: 'source', weight: 10, urls: ['https://example.com/article-1'], sentiment: 'positive' },
    ],
    edges: [
      { source: 'topic', target: 'theme:performance', kind: 'theme', weight: 8 },
      { source: 'theme:performance', target: 'source:example.com', kind: 'source', weight: 4 },
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
  `data: ${JSON.stringify({ type: 'fetch_started', detail: { url_count: 3, elapsed_ms: 1000 }, message: 'Fetching 3 URLs', ts: Date.now() })}\n\n`,
  `data: ${JSON.stringify({ type: 'url_fetched', detail: { url: 'https://example.com/a', domain: 'example.com', item_count: 2, fetch_ms: 120, elapsed_ms: 1100 }, message: 'Fetched 2 items', ts: Date.now() })}\n\n`,
  `data: ${JSON.stringify({ type: 'url_fetched', detail: { url: 'https://example.com/b', domain: 'example.com', item_count: 1, fetch_ms: 130, elapsed_ms: 1200 }, message: 'Fetched 1 item', ts: Date.now() })}\n\n`,
  `data: ${JSON.stringify({ type: 'url_fetched', detail: { url: 'https://example.com/c', domain: 'example.com', item_count: 1, fetch_ms: 140, elapsed_ms: 1300 }, message: 'Fetched 1 item', ts: Date.now() })}\n\n`,
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

  // Run hydration for restored/history tabs
  await page.route(`**/api/runs/${RUN_ID}`, (r: Route) =>
    r.fulfill({
      status: 200,
      json: {
        id: RUN_ID,
        topic: 'test product',
        freshness: 'pm',
        research_depth: 'standard',
        status: 'completed',
        created_at: new Date().toISOString(),
        report: MOCK_REPORT,
      },
    }),
  )

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

  test('freshness options are chronological', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    const labels = await page.locator('.freshness-select option').allTextContents()
    expect(labels).toEqual(['Past 24 h', 'Past week', 'Past month', 'Past year', 'Any time'])
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

  test('timeline has one run start and expanded fetch list pushes rows down', async ({ page }) => {
    await expect(page.locator('section[aria-label="Run timeline"]')).toBeVisible({ timeout: 10_000 })

    await expect(page.locator('.timeline-event--run_started')).toHaveCount(1)
    await page.locator('.url-expand-toggle').click()
    const fetchBox = await page.locator('.timeline-event--fetch_started').boundingBox()
    const doneBox = await page.locator('.timeline-event--run_completed').boundingBox()
    expect(fetchBox).not.toBeNull()
    expect(doneBox).not.toBeNull()
    expect(doneBox!.y).toBeGreaterThan(fetchBox!.y + fetchBox!.height - 1)
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
    await expect(page.locator('.source-time-chart')).toBeVisible()
    await expect(page.locator('.location-map')).toBeVisible()
  })

  test('expanded search keeps the previous report visible until the new report finishes', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.route(`**/api/runs/${RUN_ID}/expand`, (r: Route) =>
      r.fulfill({ status: 200, json: { run_id: EXPAND_RUN_ID } }),
    )
    await page.route(`**/api/runs/${EXPAND_RUN_ID}/events**`, async (r: Route) => {
      await new Promise(resolve => setTimeout(resolve, 600))
      return r.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: ${JSON.stringify({ type: 'run_started', detail: {}, ts: Date.now() })}\n\n`,
      })
    })

    await page.locator('.btn-expand').click()
    await expect(page.locator('.expanded-run-badge')).toBeVisible()
    await expect(page.locator('.narrative')).toContainText('Overall sentiment is positive')
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

  test('Graph tab renders SVG and opens theme detail popover', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Graph")').click()
    await expect(page.locator('.idea-graph')).toBeVisible()
    await expect(page.locator('.graph-detail-panel')).toBeVisible()
    await expect(page.locator('.graph-node').first()).toBeVisible()
    await page.locator('.graph-node').filter({ hasText: 'performance' }).locator('circle').first().click()
    await expect(page.locator('.topic-detail-popover')).toBeVisible()
    await expect(page.locator('.topic-detail-title')).toContainText('performance')
  })

  test('Topics tab opens thread detail with verifiable sources', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    await page.locator('button[role="tab"]:has-text("Topics")').click()
    await page.locator('.thread-card', { hasText: 'battery life' }).click()
    await expect(page.locator('.thread-detail')).toBeVisible()
    await expect(page.locator('.thread-detail')).toContainText('Great battery life')
    await expect(page.locator('.thread-detail-sources a')).toBeVisible()
  })

  test('export buttons download JSON, CSV, and Markdown files', async ({ page }) => {
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })

    for (const label of ['JSON', 'CSV', 'MD']) {
      const downloadPromise = page.waitForEvent('download')
      await page.locator('.export-actions button', { hasText: label }).click()
      const download = await downloadPromise
      expect(download.suggestedFilename()).toMatch(/test-product\.(json|csv|md)$/)
    }
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

test.describe('Session restore', () => {
  test('hydrates topic and report for a completed run tab', async ({ page }) => {
    await mockBackend(page)
    await page.addInitScript(({ runId }) => {
      localStorage.setItem('autosentiment_session', JSON.stringify({
        activeId: 'tab-1',
        tabs: [{ id: 'tab-1', label: 'test product', status: 'completed', runId }],
      }))
    }, { runId: RUN_ID })

    await page.goto('/')

    await expect(page.locator('.run-topic')).toContainText('test product', { timeout: 10_000 })
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible()
  })
})

test.describe('Shareable URL (?run=<id>)', () => {
  test('loads a completed run report from query param', async ({ page }) => {
    await mockBackend(page)
    await page.goto(`/?run=${RUN_ID}`)

    // Report should be visible without needing to submit anything.
    await expect(page.locator('section[aria-label="Report"]')).toBeVisible({ timeout: 10_000 })
    // The topic is "test product" from the mock run hydration.
    await expect(page.locator('.run-topic')).toContainText('test product')
  })
})

test.describe('Compare mode', () => {
  test('opens compare tab and renders side-by-side inputs', async ({ page }) => {
    await mockBackend(page)

    // Create runs for compare mode
    await page.route('**/api/runs', (r: Route) => {
      if (r.request().method() === 'POST')
        return r.fulfill({ status: 200, json: { run_id: RUN_ID, cached: false } })
      return r.continue()
    })

    await page.goto('/')

    // Click the Compare button in the header
    await page.locator('button:has-text("Compare")').click()

    // Should show the compare view with at least two topic inputs.
    await expect(page.locator('.compare-view')).toBeVisible()
    const inputCount = await page.locator('.compare-form-input').count()
    expect(inputCount).toBeGreaterThanOrEqual(2)
  })
})

test.describe('Keyboard shortcuts', () => {
  test('Ctrl+T opens a new search tab', async ({ page }) => {
    await mockBackend(page)
    await page.goto('/')

    const initialTabCount = await page.locator('.tab').count()

    await page.keyboard.press('Control+t')

    const newTabCount = await page.locator('.tab').count()
    expect(newTabCount).toBe(initialTabCount + 1)
  })
})

test.describe('Saved searches', () => {
  const SAVED_SEARCH = {
    id: 'ss-1',
    name: 'My saved topic',
    topic: 'electric vehicles',
    freshness: 'pw' as const,
    research_depth: 'standard' as const,
    use_case: 'generic' as const,
    created_at: new Date().toISOString(),
  }

  test('loads a saved search into the form when clicked', async ({ page }) => {
    await mockBackend(page)

    // Override the empty saved-searches stub with one that has a real entry.
    await page.route('**/api/saved-searches', (r: Route) => {
      if (r.request().method() === 'GET')
        return r.fulfill({ status: 200, json: [SAVED_SEARCH] })
      return r.continue()
    })

    await page.goto('/')

    // The Saved (1) button should be enabled.
    const savedBtn = page.locator('button:has-text("Saved")')
    await expect(savedBtn).toBeVisible()
    await expect(savedBtn).toBeEnabled()
    await savedBtn.click()

    // Dropdown is open — click the saved item.
    await expect(page.locator('.saved-dropdown')).toBeVisible()
    await page.locator('.saved-item-load').first().click()

    // Topic input should now contain the saved topic.
    await expect(page.locator('.search-input')).toHaveValue('electric vehicles')
  })

  test('saves a search and it appears in the dropdown', async ({ page }) => {
    await mockBackend(page)

    let postCalled = false
    await page.route('**/api/saved-searches', async (r: Route) => {
      if (r.request().method() === 'POST') {
        postCalled = true
        return r.fulfill({ status: 200, json: SAVED_SEARCH })
      }
      // After save, return the new entry in the list.
      return r.fulfill({ status: 200, json: postCalled ? [SAVED_SEARCH] : [] })
    })

    await page.goto('/')

    // Type a topic so the Save button enables.
    await page.locator('.search-input').fill('electric vehicles')

    // Click ★ Save to open the save name input.
    await page.locator('.btn-save-search').click()
    await expect(page.locator('.save-search-input')).toBeVisible()

    // Enter a name and submit.
    await page.locator('.save-search-input').fill('My saved topic')
    await page.locator('.save-search-form button[type="submit"]').click()

    // Save input should close, and the Saved (1) button should be enabled.
    await expect(page.locator('.save-search-input')).not.toBeVisible()
    await expect(page.locator('button:has-text("Saved (1)")')).toBeEnabled()
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

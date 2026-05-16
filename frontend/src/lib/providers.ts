export const SOURCE_TYPE_LABEL: Record<string, string> = {
  reddit: 'Reddit',
  news:   'News Media',
  social: 'Social Media',
  forum:  'Forums',
  video:  'Video',
  web:    'Web / Blogs',
}

export const KNOWN_PROVIDERS: Record<string, string> = {
  'reddit.com': 'Reddit', 'news.ycombinator.com': 'Hacker News', 'youtube.com': 'YouTube',
  'x.com': 'X / Twitter', 'twitter.com': 'X / Twitter', 'threads.net': 'Threads',
  'quora.com': 'Quora', 'facebook.com': 'Facebook', 'linkedin.com': 'LinkedIn',
  'tiktok.com': 'TikTok', 'nytimes.com': 'NY Times', 'bbc.com': 'BBC', 'bbc.co.uk': 'BBC',
  'theverge.com': 'The Verge', 'techcrunch.com': 'TechCrunch', 'wired.com': 'Wired',
  'bloomberg.com': 'Bloomberg', 'reuters.com': 'Reuters', 'wsj.com': 'WSJ',
  'apnews.com': 'AP News', 'cnn.com': 'CNN', 'insideevs.com': 'InsideEVs',
  'finance.yahoo.com': 'Yahoo Finance', 'seekingalpha.com': 'Seeking Alpha',
  'marketwatch.com': 'MarketWatch', 'fool.com': 'Motley Fool', 'cnbc.com': 'CNBC',
  'investopedia.com': 'Investopedia', 'benzinga.com': 'Benzinga', 'barrons.com': "Barron's",
  'ft.com': 'Financial Times', 'economist.com': 'The Economist',
  'sec.gov': 'SEC Filing', 'investors.com': "Investor's Business Daily",
  'tipranks.com': 'TipRanks', 'stocktwits.com': 'StockTwits',
}

export function domainFromUrl(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}

export function providerName(url: string): string {
  const d = domainFromUrl(url)
  for (const key of Object.keys(KNOWN_PROVIDERS)) {
    if (d === key || d.endsWith(`.${key}`)) return KNOWN_PROVIDERS[key]
  }
  return d.replace(/^(www|m|old|new)\./i, '')
}

export function faviconUrl(url: string): string {
  return `https://www.google.com/s2/favicons?domain=${domainFromUrl(url)}&sz=16`
}

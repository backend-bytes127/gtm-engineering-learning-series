// ---- constants (port of pipeline/constants.py) ----
const LEGAL_SUFFIXES = ['private limited', 'pvt ltd', 'pvt. ltd.', 'pvt. ltd', 'pvt ltd.', 'pte. ltd.',
  'pte ltd', 'pte. ltd', 'limited', 'ltd', 'ltd.', 'inc.', 'inc', 'llc', 'pvt', 'corp'];
const CREDENTIALS = new Set(['mba', 'pmp', 'cspo', 'phd', 'cfa', 'cpa', 'csm', 'pmi', 'cissp']);
const SALUTATIONS = new Set(['mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'sir', 'ca']);
const FIRST_NAME_ALIASES = { vicky: 'vikram', kate: 'katherine', mohd: 'mohammed', mohammad: 'mohammed',
  srinivas: 'shrinivas', laxmi: 'lakshmi' };
const PERSONAL_EMAIL_DOMAINS = new Set(['gmail.com', 'yahoo.com', 'yahoo.co.in', 'outlook.com', 'hotmail.com',
  'icloud.com', 'rediffmail.com', 'proton.me', 'protonmail.com', 'live.com', 'aol.com']);
const GENERIC_MAILBOXES = new Set(['info', 'contact', 'sales', 'hello', 'support', 'admin', 'office', 'mail',
  'enquiries', 'marketing', 'careers', 'hr']);
const PLACEHOLDER_EMAILS = new Set(['email_not_unlocked@domain.com']);
const INVALID_EMAIL_DOMAIN_SUFFIXES = ['.invalid', '.test', '.example'];
const TEST_EMAIL_DOMAINS = new Set(['test.com', 'asdf.invalid', 'google-test.invalid', 'example.com']);
const PLACEHOLDER_PHONES = new Set(['na', 'n/a', '-', 'not shared', 'none', 'null', '']);
const CITY_INFO = {
  bengaluru: ['Bengaluru', 'India'], bangalore: ['Bengaluru', 'India'], blr: ['Bengaluru', 'India'],
  'bangalore urban': ['Bengaluru', 'India'], mumbai: ['Mumbai', 'India'], bombay: ['Mumbai', 'India'],
  delhi: ['Delhi', 'India'], 'new delhi': ['New Delhi', 'India'], 'delhi ncr': ['Delhi', 'India'],
  noida: ['Noida', 'India'], gurugram: ['Gurugram', 'India'], gurgaon: ['Gurugram', 'India'],
  pune: ['Pune', 'India'], hyderabad: ['Hyderabad', 'India'], hyd: ['Hyderabad', 'India'],
  chennai: ['Chennai', 'India'], madras: ['Chennai', 'India'], kolkata: ['Kolkata', 'India'],
  calcutta: ['Kolkata', 'India'], ahmedabad: ['Ahmedabad', 'India'], amdavad: ['Ahmedabad', 'India'],
  dubai: ['Dubai', 'United Arab Emirates'], dxb: ['Dubai', 'United Arab Emirates'],
  singapore: ['Singapore', 'Singapore'], sg: ['Singapore', 'Singapore'],
  london: ['London', 'United Kingdom'], manchester: ['Manchester', 'United Kingdom'],
  'new york': ['New York', 'United States'], nyc: ['New York', 'United States'],
  'san francisco': ['San Francisco', 'United States'], sf: ['San Francisco', 'United States'],
  austin: ['Austin', 'United States'], boston: ['Boston', 'United States'],
};
const CITY_KEYWORDS = ['bengaluru', 'bangalore', 'mumbai', 'delhi', 'noida', 'gurugram', 'gurgaon', 'pune',
  'hyderabad', 'chennai', 'madras', 'kolkata', 'calcutta', 'ahmedabad', 'amdavad', 'dubai', 'singapore',
  'london', 'manchester', 'new york', 'san francisco', 'austin', 'boston'];
const COUNTRY_ALIASES = { in: 'India', india: 'India', ae: 'United Arab Emirates', uae: 'United Arab Emirates',
  'united arab emirates': 'United Arab Emirates', sg: 'Singapore', singapore: 'Singapore', gb: 'United Kingdom',
  uk: 'United Kingdom', 'united kingdom': 'United Kingdom', england: 'United Kingdom', us: 'United States',
  usa: 'United States', 'united states': 'United States' };
const COUNTRY_ISO = { India: 'IN', 'United Arab Emirates': 'AE', Singapore: 'SG', 'United Kingdom': 'GB',
  'United States': 'US' };
const TOKEN_EXPANSIONS = {
  mgr: ['manager'], dir: ['director'], sr: ['senior'], vp: ['vice', 'president'], mktg: ['marketing'],
  biz: ['business'], dev: ['development'], gen: ['generation'], demandgen: ['demand', 'generation'],
  rev: ['revenue'], revops: ['revenue', 'operations'], sdr: ['sales', 'development'], purchase: ['procurement'],
  ceo: ['chief', 'executive', 'officer'], cto: ['chief', 'technology', 'officer'],
  cro: ['chief', 'revenue', 'officer'], cmo: ['chief', 'marketing', 'officer'],
  coo: ['chief', 'operating', 'officer'], cfo: ['chief', 'financial', 'officer'], it: ['information', 'technology'],
};
const TITLE_DROP_TOKENS = new Set(['of', 'and', 'the', 'team', 'for', 'co', 'founder', 'cofounder']);
const SIZE_BUCKETS = [[10, '1-10'], [50, '11-50'], [200, '51-200'], [500, '201-500'], [1000, '501-1,000'],
  [5000, '1,001-5,000'], [10000, '5,001-10,000']];
const SIZE_TOP = '10,001+';

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  BookOpen,
  Brain,
  CalendarClock,
  CandlestickChart,
  CircleDot,
  ClipboardCheck,
  Clock3,
  Cpu,
  DatabaseZap,
  FileBarChart,
  Gauge,
  HeartPulse,
  LineChart,
  ListChecks,
  Radio,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  Target,
  TrendingDown,
  TrendingUp,
  Wifi,
  Zap,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type TerminalStock = {
  stock: string;
  symbol: string;
  sector: string;
  industry?: string;
  live_price: number;
  entry_price: number;
  stop_loss: number;
  target1: number;
  target2: number;
  target3: number;
  rrr: string;
  ml_score: number;
  technical_score: number;
  fundamental_score: number;
  confidence_pct: number;
  volume_strength: string;
  breakout_strength: string;
  pattern: string;
  trend: string;
  action: 'BUY' | 'SELL' | 'HOLD' | 'WATCH';
  reason: string;
  generated_at: string;
  last_updated: string;
  tag: 'premarket' | 'intraday' | 'swing' | 'watchlist';
  gapPercent?: number;
  change?: number;
  risk_score?: number;
  reward_potential?: number;
};

export const dashboardPanels = [
  { title: 'Premarket Recommendations', subtitle: 'Gap, volume, news, and ML qualified', filter: 'premarket' },
  { title: 'Intraday Opportunities', subtitle: 'Live breakouts and VWAP reclaims', filter: 'intraday' },
  { title: 'Swing Opportunities', subtitle: 'Multi-day momentum and base breakouts', filter: 'swing' },
  { title: 'High Confidence Trades', subtitle: 'Confidence score above 85%', filter: 'confidence' },
];

export const scanTypes = [
  'Premarket',
  'Intraday',
  'Swing',
  'Watchlist',
  'Sector Scan',
  'Industry Scan',
  'Full NSE Scan',
  'Custom Scan',
];

export const analysisModules = [
  'Gap Up Analysis',
  'Gap Down Analysis',
  'Volume Analysis',
  'News Impact',
  'Earnings Impact',
  'Sector Rotation',
  'Relative Strength',
  'Futures Data',
  'Option Chain',
  'ML Prediction',
];

export const settingsSections = [
  'Premarket Configuration',
  'Intraday Configuration',
  'Swing Configuration',
  'Watchlist Configuration',
  'Custom Scan Configuration',
  'ML Model Configuration',
  'Technical Analysis Configuration',
  'Fundamental Analysis Configuration',
  'Notification Configuration',
  'Data Feed Configuration',
  'API Configuration',
  'User Preferences',
  'Theme Settings',
];

export const reportCategories = [
  'Premarket Reports',
  'Intraday Reports',
  'Swing Reports',
  'Custom Scan Reports',
  'ML Reports',
  'Historical Reports',
  'Performance Reports',
];

export const architectureCards: Array<{ title: string; body: string; icon: LucideIcon }> = [
  { title: 'UX Architecture', body: 'Pinned market header, module workspaces, dual-panel scanners, report analytics, and command actions.', icon: BookOpen },
  { title: 'Component Hierarchy', body: 'Page shell, global widgets, terminal panels, metric tiles, scan controls, stock cards, grids, tables, and drawers.', icon: ListChecks },
  { title: 'State Management', body: 'Redux for shared scan/watchlist/settings state, local UI state for filters, and SWR-ready API refresh loops.', icon: DatabaseZap },
  { title: 'Real-Time Events', body: 'WebSocket topics for scan updates, price ticks, pushed candidates, health status, and validation results.', icon: Radio },
  { title: 'API Strategy', body: 'Centralized API client, typed payloads, optimistic UI for actions, retry-safe loading, and toast-backed errors.', icon: Wifi },
  { title: 'Loading & Errors', body: 'Skeleton grids, empty states, inline status badges, action-level disabled states, and recoverable notifications.', icon: AlertTriangle },
];

export const iconMap = {
  activity: Activity,
  alert: AlertTriangle,
  bar: BarChart3,
  bell: Bell,
  brain: Brain,
  calendar: CalendarClock,
  candle: CandlestickChart,
  clock: Clock3,
  cpu: Cpu,
  file: FileBarChart,
  gauge: Gauge,
  heart: HeartPulse,
  line: LineChart,
  radio: Radio,
  search: Search,
  settings: Settings,
  shield: ShieldCheck,
  sliders: SlidersHorizontal,
  spark: Sparkles,
  star: Star,
  target: Target,
  down: TrendingDown,
  up: TrendingUp,
  zap: Zap,
  dot: CircleDot,
};

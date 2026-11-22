declare module 'next' {
  export interface Metadata { title?: string; description?: string }
  export interface NextConfig { reactStrictMode?: boolean }
}
declare module 'next/dist/lib/metadata/types/metadata-interface.js' {
  export type ResolvingMetadata = any;
  export type ResolvingViewport = any;
}
declare module 'next/types.js' {
  export type AppRoutes = any;
  export type LayoutRoutes = any;
  export type ParamMap = any;
  export type ResolvingMetadata = any;
  export type ResolvingViewport = any;
}

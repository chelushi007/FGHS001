import './globals.css';
import type { Metadata } from 'next';
export const metadata:Metadata={title:'钢链智脑｜产业决策工作台',description:'废钢全链路供需协同与利益优化智能体'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>}

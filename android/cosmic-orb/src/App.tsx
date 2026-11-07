import MarbleSprite from './components/originkit/ui/cobalt-sprite'

export default function App() {
  return (
    <main className="grid min-h-screen w-full place-items-center overflow-hidden bg-[#05050f]">
      <div className="h-full w-full">
        <MarbleSprite background="#05050F" scale={88} spriteColor="#164BFF" follow="frame" />
      </div>
    </main>
  )
}

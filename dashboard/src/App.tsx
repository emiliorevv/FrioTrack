import './App.css'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>FríoTrack</h1>
        <p className="app-subtitle">Monitoreo de cadena de frío</p>
      </header>

      <main className="app-main">
        <section className="panel" aria-labelledby="panel-title">
          <h2 id="panel-title">Panel de monitoreo</h2>
          <p>
            Aquí verás el estado de las cámaras frigoríficas y del congelador en
            tiempo real.
          </p>
        </section>
      </main>
    </div>
  )
}

export default App

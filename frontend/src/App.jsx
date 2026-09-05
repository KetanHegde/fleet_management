import { useCallback, useEffect, useRef, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

function mergeTelemetry(current, incoming) {
  const next = { ...current }
  incoming.forEach((event) => {
    const existing = next[event.robot_id]
    if (!existing || event.t >= existing.t) next[event.robot_id] = event
  })
  return next
}

function App() {
  const [robots, setRobots] = useState({})
  const [roster, setRoster] = useState([])
  const [connection, setConnection] = useState('Connecting')
  const [error, setError] = useState('')
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef(null)
  const reportingRobotCount = roster.filter((robot) => robots[robot.robot_id]).length

  const refreshSnapshot = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/robots`)
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      const data = await response.json()
      setRobots((current) => mergeTelemetry(current, data.robots))
      setError('')
    } catch (snapshotError) {
      setError(`Snapshot unavailable: ${snapshotError.message}`)
    }
  }, [])

  const loadRoster = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/robots/roster`)
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      const data = await response.json()
      setRoster(data.robots)
    } catch (rosterError) {
      setError(`Robot roster unavailable: ${rosterError.message}`)
    }
  }, [])

  useEffect(() => {
    let active = true
    let socket

    const connect = () => {
      if (!active) return
      setConnection('Connecting')
      socket = new WebSocket(WS_URL)

      socket.onopen = () => {
        if (!active) return
        reconnectAttempt.current = 0
        setConnection('Live')
        refreshSnapshot()
      }
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data)
          setRobots((current) => mergeTelemetry(current, [event]))
        } catch {
          setError('Received an invalid WebSocket event')
        }
      }
      socket.onclose = () => {
        if (!active) return
        const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 30000)
        reconnectAttempt.current += 1
        setConnection(`Reconnecting in ${delay / 1000}s`)
        reconnectTimer.current = window.setTimeout(connect, delay)
      }
      socket.onerror = () => socket.close()
    }

    loadRoster()
    refreshSnapshot()
    connect()
    return () => {
      active = false
      window.clearTimeout(reconnectTimer.current)
      socket?.close()
    }
  }, [loadRoster, refreshSnapshot])

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">FLEET OBSERVABILITY</p>
          <h1>Robot Fleet Monitor</h1>
        </div>
        <div className="dashboard-status">
          <div className={`connection ${connection === 'Live' ? 'live' : ''}`}>{connection}</div>
          <p className="telemetry-summary">Telemetry: {reportingRobotCount}/{roster.length || 8} robots reporting</p>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      <section className="robot-grid" aria-label="Robot telemetry">
        {roster.map((rosterRobot) => {
          const robot = robots[rosterRobot.robot_id]
          return (
            <article className="robot-card" key={rosterRobot.robot_id}>
              <div className="card-heading">
                <div><h2>{rosterRobot.robot_id}</h2><p className="robot-type">{rosterRobot.robot_type}</p></div>
                <span>{robot?.status || 'Awaiting telemetry'}</span>
              </div>
              <p className="start">Recorded start: {rosterRobot.start.x.toFixed(1)}, {rosterRobot.start.y.toFixed(1)}</p>
              {robot ? (
                <dl>
                  <div><dt>Position</dt><dd>{robot.x.toFixed(1)}, {robot.y.toFixed(1)}</dd></div>
                  <div><dt>Battery</dt><dd>{robot.battery.toFixed(1)}%</dd></div>
                </dl>
              ) : <p className="empty">No event received yet.</p>}
            </article>
          )
        })}
      </section>
    </main>
  )
}

export default App

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
const MAP_WIDTH = 900
const MAP_HEIGHT = 560

const STATUS_META = {
  idle: { label: 'Idle', color: '#64748b' },
  active: { label: 'Active', color: '#0f8fdb' },
  on_mission: { label: 'On mission', color: '#7c3aed' },
  charging: { label: 'Charging', color: '#c58a06' },
  blocked: { label: 'Blocked', color: '#e06c00' },
  error: { label: 'Error', color: '#dc2626' },
  maintenance: { label: 'Maintenance', color: '#9a4dba' },
  offline: { label: 'Offline', color: '#475569' },
  awaiting: { label: 'Awaiting telemetry', color: '#94a3b8' },
}

function mergeTelemetry(current, incoming) {
  const next = { ...current }
  incoming.forEach((event) => {
    const existing = next[event.robot_id]
    if (!existing || event.t >= existing.t) next[event.robot_id] = event
  })
  return next
}

function statusFor(robot) {
  return STATUS_META[robot?.status] || STATUS_META.awaiting
}

function robotPosition(rosterRobot, telemetry) {
  return telemetry ? { x: telemetry.x, y: telemetry.y } : rosterRobot.start
}

function mapPoint(position) {
  return {
    left: `${Math.max(0, Math.min(MAP_WIDTH, position.x)) / MAP_WIDTH * 100}%`,
    top: `${Math.max(0, Math.min(MAP_HEIGHT, position.y)) / MAP_HEIGHT * 100}%`,
  }
}

function App() {
  const [robots, setRobots] = useState({})
  const [roster, setRoster] = useState([])
  const [selectedRobotId, setSelectedRobotId] = useState(null)
  const [connection, setConnection] = useState('Connecting')
  const [error, setError] = useState('')
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef(null)
  const reportingRobotCount = roster.filter((robot) => robots[robot.robot_id]).length

  const selectedRosterRobot = useMemo(
    () => roster.find((robot) => robot.robot_id === selectedRobotId) || roster[0],
    [roster, selectedRobotId],
  )
  const selectedTelemetry = selectedRosterRobot ? robots[selectedRosterRobot.robot_id] : null
  const selectedStatus = statusFor(selectedTelemetry)
  const selectedPosition = selectedRosterRobot ? robotPosition(selectedRosterRobot, selectedTelemetry) : null

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
      setSelectedRobotId((current) => current || data.robots[0]?.robot_id || null)
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
    <main className="fleet-dashboard">
      <header className="page-header">
        <div>
          <p className="eyebrow">LOCAL FLEET OBSERVABILITY</p>
          <h1>Fleet control room</h1>
          <p className="subheading">Live robot locations are shown against the warehouse plan.</p>
        </div>
        <div className="header-status">
          <div className={`connection ${connection === 'Live' ? 'live' : ''}`}>{connection}</div>
          <p className="telemetry-summary">Telemetry: <strong>{reportingRobotCount}/{roster.length || 8}</strong> robots reporting</p>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="control-room" aria-label="Fleet map and selected robot details">
        <div className="map-section">
          <div className="map-heading">
            <div><h2>Facility map</h2><p>Origin is the top-left corner: 0, 0</p></div>
            <div className="legend" aria-label="Robot status color legend">
              {Object.entries(STATUS_META).filter(([status]) => status !== 'awaiting').map(([status, meta]) => (
                <span key={status}><i style={{ backgroundColor: meta.color }} />{meta.label}</span>
              ))}
            </div>
          </div>

          <div className="map-viewport">
            <div className="facility-map" aria-label="900 by 560 unit warehouse map">
              <div className="obstacle obstacle-top-left" aria-hidden="true" />
              <div className="obstacle obstacle-mid-left" aria-hidden="true" />
              <div className="obstacle obstacle-bottom-left" aria-hidden="true" />
              <div className="obstacle obstacle-center" aria-hidden="true" />
              <div className="obstacle obstacle-top-right" aria-hidden="true" />
              <div className="obstacle obstacle-bottom-right" aria-hidden="true" />

              <span className="map-origin">0, 0</span>
              <span className="map-scale">900×560 px · 1 px = 1 unit</span>

              {roster.map((rosterRobot) => {
                const telemetry = robots[rosterRobot.robot_id]
                const status = statusFor(telemetry)
                const position = robotPosition(rosterRobot, telemetry)
                const isSelected = rosterRobot.robot_id === selectedRosterRobot?.robot_id
                const tooltipPlacement = [
                  position.y < 130 ? 'tooltip-below' : '',
                  position.x < 140 ? 'tooltip-right' : '',
                  position.x > 760 ? 'tooltip-left' : '',
                ].filter(Boolean).join(' ')
                return (
                  <button
                    aria-label={`Select ${rosterRobot.robot_id}, ${status.label}`}
                    className={`robot-marker ${isSelected ? 'selected' : ''} ${tooltipPlacement}`}
                    key={rosterRobot.robot_id}
                    onClick={() => setSelectedRobotId(rosterRobot.robot_id)}
                    style={{ ...mapPoint(position), '--robot-color': status.color }}
                    type="button"
                  >
                    <span className="marker-dot" />
                    <span className="marker-label">{rosterRobot.robot_id}</span>
                    <span className="robot-tooltip" role="tooltip">
                      <span className="tooltip-heading"><strong>{rosterRobot.robot_id}</strong><em>{rosterRobot.robot_type}</em></span>
                      <span className="tooltip-status" style={{ '--robot-color': status.color }}><i />{status.label}</span>
                      <span className="tooltip-row"><small>Position</small><b>{position.x.toFixed(1)}, {position.y.toFixed(1)}</b></span>
                      <span className="tooltip-row"><small>Battery</small><b>{telemetry ? `${telemetry.battery.toFixed(1)}%` : 'Awaiting telemetry'}</b></span>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        <aside className="details-panel" aria-live="polite">
          {selectedRosterRobot ? (
            <>
              <div className="details-heading">
                <p>Selected robot</p>
                <h2>{selectedRosterRobot.robot_id}</h2>
                <span className="type-label">{selectedRosterRobot.robot_type}</span>
              </div>
              <div className="status-card" style={{ '--robot-color': selectedStatus.color }}>
                <span className="status-dot" />
                <div><small>Current status</small><strong>{selectedStatus.label}</strong></div>
              </div>
              <dl className="robot-details">
                <div><dt>{selectedTelemetry ? 'Current position' : 'Recorded start'}</dt><dd>{selectedPosition.x.toFixed(1)}, {selectedPosition.y.toFixed(1)}</dd></div>
                <div><dt>Battery</dt><dd>{selectedTelemetry ? `${selectedTelemetry.battery.toFixed(1)}%` : 'Awaiting telemetry'}</dd></div>
                {selectedTelemetry && <div><dt>Recorded start</dt><dd>{selectedRosterRobot.start.x.toFixed(1)}, {selectedRosterRobot.start.y.toFixed(1)}</dd></div>}
              </dl>
              <div className="robot-picker" aria-label="Select a robot">
                <p>All robots</p>
                <div>
                  {roster.map((robot) => {
                    const status = statusFor(robots[robot.robot_id])
                    return (
                      <button
                        className={robot.robot_id === selectedRosterRobot.robot_id ? 'active' : ''}
                        key={robot.robot_id}
                        onClick={() => setSelectedRobotId(robot.robot_id)}
                        style={{ '--robot-color': status.color }}
                        type="button"
                      >
                        <i />{robot.robot_id}
                      </button>
                    )
                  })}
                </div>
              </div>
            </>
          ) : <p className="loading-details">Loading robot roster…</p>}
        </aside>
      </section>
    </main>
  )
}

export default App

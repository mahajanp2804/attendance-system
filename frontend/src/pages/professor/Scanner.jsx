import { useEffect, useRef, useState, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import api from '../../hooks/api'

const WS_URL = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000')

export default function ProfScanner() {
  const location = useLocation()
  const preselectedSlot = location.state?.slotId

  const videoRef   = useRef(null)
  const canvasRef  = useRef(null)
  const wsRef      = useRef(null)
  const loopRef    = useRef(null)
  const inFlightRef = useRef(0)   // send time of the frame awaiting a reply, 0 if none

  const [slots,       setSlots]       = useState([])
  const [selectedSlot,setSelectedSlot]= useState(preselectedSlot || '')
  const [sessionId,   setSessionId]   = useState(null)
  const [scanning,    setScanning]    = useState(false)
  const [connected,   setConnected]   = useState(false)
  const [result,      setResult]      = useState(null)
  const [faces,       setFaces]       = useState([])
  const [error,       setError]       = useState('')
  const [camReady,    setCamReady]    = useState(false)

  // Load today's slots
  useEffect(() => {
    api.get('/api/timetable/today').then(r => setSlots(r.data))
  }, [])

  // Start camera
  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      })
      videoRef.current.srcObject = stream
      setCamReady(true)
    } catch (e) {
      setError('Camera access denied. Please allow camera permissions.')
    }
  }, [])

  // Open session + connect WebSocket
  const startSession = async () => {
    if (!selectedSlot) { setError('Select a class first'); return }
    setError('')
    try {
      // Create class session
      const today = new Date().toISOString().split('T')[0]
      const res = await api.post('/api/attendance/sessions', { slot_id: selectedSlot, date: today })
      const sid = res.data.id
      setSessionId(sid)

      // Connect WebSocket
      const token = localStorage.getItem('access_token')
      const ws = new WebSocket(`${WS_URL}/api/recognition/ws/${sid}`)
      wsRef.current = ws

      ws.onopen = () => {
        ws.send(token)   // auth handshake
      }
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'connected') {
          setConnected(true)
          setScanning(true)
          startFrameLoop()
        } else if (msg.type === 'skipped') {
          inFlightRef.current = 0
        } else if (msg.type === 'result') {
          inFlightRef.current = 0
          setResult(msg)
          setFaces(msg.faces || [])
          drawOverlay(msg.faces || [])
        } else if (msg.type === 'error') {
          setError(msg.message)
        }
      }
      ws.onclose = () => { setConnected(false); setScanning(false) }
      ws.onerror = () => setError('WebSocket connection failed')
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to start session')
    }
  }

  // Send frames via WebSocket
  const startFrameLoop = () => {
    const canvas = document.createElement('canvas')
    const FPS = 3   // 3 frames/sec is sufficient for classroom scan
    const REPLY_TIMEOUT_MS = 5000   // give up waiting on a reply after this
    inFlightRef.current = 0

    loopRef.current = setInterval(() => {
      const video = videoRef.current
      if (!video || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
      // Wait for the previous frame's result, so frames don't pile up when the server is slower than FPS
      if (inFlightRef.current && Date.now() - inFlightRef.current < REPLY_TIMEOUT_MS) return
      inFlightRef.current = Date.now()

      canvas.width  = video.videoWidth
      canvas.height = video.videoHeight
      canvas.getContext('2d').drawImage(video, 0, 0)
      canvas.toBlob(blob => {
        if (blob && wsRef.current?.readyState === WebSocket.OPEN) {
          blob.arrayBuffer().then(buf => wsRef.current.send(buf))
        } else {
          inFlightRef.current = 0
        }
      }, 'image/jpeg', 0.85)
    }, 1000 / FPS)
  }

  // Draw bounding box overlay
  const drawOverlay = (faceList) => {
    const canvas = canvasRef.current
    const video  = videoRef.current
    if (!canvas || !video) return
    canvas.width  = video.videoWidth  || video.clientWidth
    canvas.height = video.videoHeight || video.clientHeight
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    const scaleX = canvas.width  / (video.videoWidth  || canvas.width)
    const scaleY = canvas.height / (video.videoHeight || canvas.height)

    faceList.forEach(face => {
      if (!face.box) return
      const [x1, y1, x2, y2] = face.box
      const color = face.status === 'recognised'
        ? (face.already_marked ? '#16A34A' : '#2563EB')
        : face.status === 'low_confidence' ? '#D97706' : '#DC2626'

      ctx.strokeStyle = color
      ctx.lineWidth   = 2
      ctx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY)

      if (face.name) {
        ctx.fillStyle = color
        ctx.fillRect(x1 * scaleX, (y1 - 22) * scaleY, (x2 - x1) * scaleX, 22)
        ctx.fillStyle = '#fff'
        ctx.font = '12px Inter, sans-serif'
        ctx.fillText(
          `${face.name} ${Math.round(face.confidence * 100)}%`,
          (x1 + 4) * scaleX,
          (y1 - 6) * scaleY
        )
      }
    })
  }

  // Close session
  const stopSession = async () => {
    clearInterval(loopRef.current)
    if (wsRef.current) { wsRef.current.send(JSON.stringify({ action: 'close' })); wsRef.current.close() }
    if (sessionId) {
      await api.patch(`/api/attendance/sessions/${sessionId}/close`)
    }
    setScanning(false); setConnected(false); setSessionId(null)
    setResult(null); setFaces([])
    const ctx = canvasRef.current?.getContext('2d')
    ctx?.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height)
  }

  useEffect(() => {
    startCamera()
    return () => {
      clearInterval(loopRef.current)
      wsRef.current?.close()
      videoRef.current?.srcObject?.getTracks().forEach(t => t.stop())
    }
  }, [])

  const recognised = faces.filter(f => f.status === 'recognised')
  const unknown    = faces.filter(f => f.status !== 'recognised')

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-text-primary">Scan Class</h1>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
      )}

      {/* Class selector */}
      {!scanning && (
        <div className="card space-y-3">
          <div>
            <label className="label">Select today's class</label>
            <select
              className="input"
              value={selectedSlot}
              onChange={e => setSelectedSlot(e.target.value)}
            >
              <option value="">-- Choose a class --</option>
              {slots.map(s => (
                <option key={s.id} value={s.id}>
                  {s.subject_name} ({s.start_time} – {s.end_time}) · {s.room}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn-primary w-full"
            onClick={startSession}
            disabled={!selectedSlot || !camReady}
          >
            {camReady ? 'Start scanning' : 'Starting camera…'}
          </button>
        </div>
      )}

      {/* Live counter */}
      {scanning && result && (
        <div className="grid grid-cols-3 gap-3">
          <div className="card text-center">
            <p className="text-2xl font-bold text-primary">{result.present_count}</p>
            <p className="text-xs text-text-muted">Present</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-danger">
              {(result.total_enrolled || 0) - result.present_count}
            </p>
            <p className="text-xs text-text-muted">Not yet</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-text-secondary">{result.total_enrolled}</p>
            <p className="text-xs text-text-muted">Enrolled</p>
          </div>
        </div>
      )}

      {/* Camera feed */}
      <div className="card p-0 overflow-hidden relative rounded-xl bg-black">
        <video
          ref={videoRef}
          autoPlay playsInline muted
          className="w-full rounded-xl"
          style={{ maxHeight: '60vw', objectFit: 'cover' }}
        />
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full"
          style={{ pointerEvents: 'none' }}
        />
        {scanning && (
          <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 text-white text-xs px-2 py-1 rounded-full">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            Live scanning
          </div>
        )}
      </div>

      {/* Recognised list */}
      {scanning && recognised.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold mb-2 text-text-primary">Recognised this frame</h2>
          <div className="space-y-1">
            {recognised.map((f, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b border-surface-border last:border-0">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${f.already_marked ? 'bg-success' : 'bg-primary'}`} />
                  <p className="text-sm font-medium text-text-primary">{f.name}</p>
                  <p className="text-xs text-text-muted">{f.roll_number}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted">{Math.round(f.confidence * 100)}%</span>
                  {f.already_marked
                    ? <span className="badge badge-green">Marked</span>
                    : <span className="badge badge-blue">New ✓</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* End session button */}
      {scanning && (
        <button className="btn-danger w-full" onClick={stopSession}>
          End session & finalise attendance
        </button>
      )}
    </div>
  )
}

import * as THREE from 'three'

/**
 * 背景：粒子星云 + 缓慢旋转的线框球
 * 低开销：粒子用 Points，球用 LineSegments，都只渲染一次几何体
 */
export function initBackground(canvas: HTMLCanvasElement) {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance',
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(window.innerWidth, window.innerHeight)

  const scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x05070d, 0.0009)

  const camera = new THREE.PerspectiveCamera(
    60,
    window.innerWidth / window.innerHeight,
    0.1,
    2000,
  )
  camera.position.set(0, 0, 320)

  // ---------- 1. 粒子星云 ----------
  const COUNT = 2600
  const positions = new Float32Array(COUNT * 3)
  const colors = new Float32Array(COUNT * 3)
  const sizes = new Float32Array(COUNT)

  const palette = [
    new THREE.Color('#60a5fa'),
    new THREE.Color('#818cf8'),
    new THREE.Color('#22d3ee'),
    new THREE.Color('#c4b5fd'),
    new THREE.Color('#f9a8d4'),
    new THREE.Color('#7dd3fc'),
  ]

  for (let i = 0; i < COUNT; i++) {
    // 球壳分布，避免中心过密
    const r = 220 + Math.pow(Math.random(), 0.6) * 620
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)

    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = r * Math.cos(phi) * 0.55
    positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta)

    const c = palette[(Math.random() * palette.length) | 0]
    colors[i * 3] = c.r
    colors[i * 3 + 1] = c.g
    colors[i * 3 + 2] = c.b
    sizes[i] = Math.random() * 2.8 + 1.1
  }

  const pGeo = new THREE.BufferGeometry()
  pGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  pGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  pGeo.setAttribute('size', new THREE.BufferAttribute(sizes, 1))

  const pMat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexColors: true,
    uniforms: { uTime: { value: 0 } },
    vertexShader: /* glsl */ `
      attribute float size;
      varying vec3 vColor;
      uniform float uTime;
      void main() {
        vColor = color;
        vec3 p = position;
        p.y += sin(uTime * 0.35 + position.x * 0.01) * 5.0;
        p.x += cos(uTime * 0.22 + position.z * 0.01) * 4.0;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = size * 1.6 * (420.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vColor;
      void main() {
        float d = length(gl_PointCoord - vec2(0.5));
        if (d > 0.5) discard;
        float a = smoothstep(0.5, 0.05, d);
        gl_FragColor = vec4(vColor, a * 1.0);
      }
    `,
  })

  const points = new THREE.Points(pGeo, pMat)
  scene.add(points)

  // 近景亮星（景深：大而亮，慢速移动）
  const NEAR = 220
  const nPos = new Float32Array(NEAR * 3)
  const nSize = new Float32Array(NEAR)
  for (let i = 0; i < NEAR; i++) {
    const r = 90 + Math.random() * 130
    const th = Math.random() * Math.PI * 2
    const ph = Math.acos(2 * Math.random() - 1)
    nPos[i * 3] = r * Math.sin(ph) * Math.cos(th)
    nPos[i * 3 + 1] = r * Math.cos(ph)
    nPos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th)
    nSize[i] = Math.random() * 3.5 + 1.5
  }
  const nGeo = new THREE.BufferGeometry()
  nGeo.setAttribute('position', new THREE.BufferAttribute(nPos, 3))
  nGeo.setAttribute('size', new THREE.BufferAttribute(nSize, 1))
  const nMat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: { uTime: { value: 0 } },
    vertexShader: /* glsl */ `
      attribute float size;
      uniform float uTime;
      void main() {
        vec3 p = position;
        p.y += sin(uTime * 0.5 + position.x * 0.03) * 7.0;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = size * (420.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      void main() {
        float d = length(gl_PointCoord - vec2(0.5));
        if (d > 0.5) discard;
        float core = smoothstep(0.5, 0.0, d);
        vec3 c = mix(vec3(0.55, 0.78, 1.0), vec3(1.0), core * core);
        gl_FragColor = vec4(c, core * 0.95);
      }
    `,
  })
  const nearPoints = new THREE.Points(nGeo, nMat)
  scene.add(nearPoints)

  // ---------- 2. 线框球 ----------
  const sphereGeo = new THREE.IcosahedronGeometry(150, 2)
  const wire = new THREE.LineSegments(
    new THREE.WireframeGeometry(sphereGeo),
    new THREE.LineBasicMaterial({
      color: 0x3b6ea8,
      transparent: true,
      opacity: 0.32,
    }),
  )
  scene.add(wire)

  const inner = new THREE.Mesh(
    sphereGeo,
    new THREE.MeshBasicMaterial({
      color: 0x060a14,
      transparent: true,
      opacity: 0.82,
    }),
  )
  scene.add(inner)

  // ---------- 3. 交互 ----------
  const pointer = { x: 0, y: 0 }
  const target = { x: 0, y: 0 }

  window.addEventListener('pointermove', (e) => {
    pointer.x = (e.clientX / window.innerWidth) * 2 - 1
    pointer.y = (e.clientY / window.innerHeight) * 2 - 1
  }, { passive: true })

  const clock = new THREE.Clock()

  function resize() {
    const w = window.innerWidth
    const h = window.innerHeight
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
  }
  window.addEventListener('resize', resize)

  let raf = 0
  function tick() {
    const t = clock.getElapsedTime()
    pMat.uniforms.uTime.value = t

    // 视差
    target.x += (pointer.x * 0.6 - target.x) * 0.03
    target.y += (-pointer.y * 0.4 - target.y) * 0.03
    camera.position.x = target.x * 26
    camera.position.y = target.y * 26
    camera.lookAt(0, 0, 0)

    nMat.uniforms.uTime.value = t
    points.rotation.y = t * 0.018
    points.rotation.x = Math.sin(t * 0.08) * 0.06
    nearPoints.rotation.y = -t * 0.03
    nearPoints.rotation.z = t * 0.008
    wire.rotation.y = -t * 0.06
    wire.rotation.x = t * 0.02
    inner.rotation.copy(wire.rotation)

    renderer.render(scene, camera)
    raf = requestAnimationFrame(tick)
  }
  tick()

  return () => {
    cancelAnimationFrame(raf)
    renderer.dispose()
    pGeo.dispose()
    pMat.dispose()
    nGeo.dispose()
    nMat.dispose()
    sphereGeo.dispose()
    wire.geometry.dispose()
    ;(wire.material as THREE.Material).dispose()
    ;(inner.material as THREE.Material).dispose()
  }
}

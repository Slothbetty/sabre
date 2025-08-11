const imageInput = document.getElementById('imageInput');
const board = document.getElementById('board');
const heightSlider = document.getElementById('heightSlider');
let currentGroup = null;

imageInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (evt) => {
    const img = new Image();
    img.onload = () => {
      const imgData = ImageTracer.getImgdata(img);
      const svgString = ImageTracer.imagedataToSVG(imgData);
      const parser = new DOMParser();
      const svgDoc = parser.parseFromString(svgString, 'image/svg+xml');
      const svgElement = svgDoc.documentElement;

      if (currentGroup) board.removeChild(currentGroup);
      currentGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      currentGroup.classList.add('draggable');
      currentGroup.appendChild(svgElement);
      board.appendChild(currentGroup);

      setupDrag(currentGroup);
    };
    img.src = evt.target.result;
  };
  reader.readAsDataURL(file);
});

function setupDrag(target) {
  let selected = null;
  let offset = { x: 0, y: 0 };

  target.addEventListener('mousedown', (e) => {
    selected = target;
    const pt = getMousePosition(e);
    const transform = selected.transform.baseVal.consolidate();
    offset.x = pt.x - (transform ? transform.matrix.e : 0);
    offset.y = pt.y - (transform ? transform.matrix.f : 0);
  });

  board.addEventListener('mousemove', (e) => {
    if (!selected) return;
    e.preventDefault();
    const pt = getMousePosition(e);
    const x = pt.x - offset.x;
    const y = pt.y - offset.y;
    selected.setAttribute('transform', `translate(${x},${y}) scale(${heightSlider.value})`);
  });

  window.addEventListener('mouseup', () => {
    selected = null;
  });
}

heightSlider.addEventListener('input', () => {
  if (currentGroup) {
    const transform = currentGroup.transform.baseVal.consolidate();
    const x = transform ? transform.matrix.e : 0;
    const y = transform ? transform.matrix.f : 0;
    currentGroup.setAttribute('transform', `translate(${x},${y}) scale(${heightSlider.value})`);
  }
});

function getMousePosition(evt) {
  const CTM = board.getScreenCTM();
  return {
    x: (evt.clientX - CTM.e) / CTM.a,
    y: (evt.clientY - CTM.f) / CTM.d,
  };
}

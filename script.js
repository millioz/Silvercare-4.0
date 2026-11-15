const slides = [
  {
    number: "01",
    kicker: "PROJECT INTRODUCTION",
    title: "SilverCare Smart Medicine Reminder Box",
    subtitle: "Technology designed to make medication management easier and safer.",
    image: "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1600",
    heading: "About Our Project",
    paragraphs: [
      "SilverCare is a smart medication reminder system designed especially for elderly people who may forget their daily medicine schedules.",
      "The project combines an ESP32 microcontroller, OLED display, buzzer, physical button, web dashboard, and Python analytics.",
      "Our goal is to create a simple and affordable system that helps users remember medication and monitor their daily habits."
    ],
    sideHeading: "Technology Stack",
    bullets: [
      "ESP32 — Main microcontroller",
      "OLED — Displays medication information",
      "Buzzer — Provides sound reminders",
      "Web Dashboard — Shows medication status",
      "Python — Analyzes medication records"
    ],
    fact: "SilverCare connects physical hardware, web technology, and Python data analysis into one healthcare support system."
  },

  {
    number: "02",
    kicker: "THE PROBLEM",
    title: "Medication Non-Adherence",
    subtitle: "Forgetting medicine can become a serious problem, especially for elderly people.",
    image: "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1600",
    heading: "What Is the Problem?",
    paragraphs: [
      "Many elderly people need to take several medicines at different times during the day.",
      "However, remembering every dose can be difficult. Some people forget whether they have already taken their medicine.",
      "Traditional paper schedules and ordinary alarms do not always provide a way to confirm whether a dose was actually taken."
    ],
    sideHeading: "Main Challenges",
    bullets: [
      "Elderly patients may forget medication times.",
      "Missed doses can negatively affect treatment.",
      "Paper schedules are difficult to monitor.",
      "Family members may not know if medicine was taken.",
      "There is limited information about daily medication habits."
    ],
    fact: "The main challenge is not simply remembering the time. It is also knowing whether the medication was taken."
  },

  {
    number: "03",
    kicker: "OUR SOLUTION",
    title: "A Smarter Way to Remember",
    subtitle: "A reminder system with user confirmation and medication tracking.",
    image: "https://images.unsplash.com/photo-1584982751601-97dcc096659c?w=1600",
    heading: "How SilverCare Helps",
    paragraphs: [
      "SilverCare provides an automatic reminder when a scheduled medication time arrives.",
      "The buzzer alerts the user, while the OLED display shows the medication reminder. The user can press a physical button after taking the medicine.",
      "If the user does not confirm the reminder within the defined time, the system records the dose as missed."
    ],
    sideHeading: "Main Features",
    bullets: [
      "Automatic medication reminders",
      "OLED screen with clear information",
      "Buzzer notification",
      "Physical TAKEN confirmation button",
      "MISSED status when there is no confirmation",
      "Web dashboard for medication monitoring"
    ],
    fact: "SilverCare does more than remind users. It also records their confirmation and missed medication events."
  },

  {
    number: "04",
    kicker: "AI-ASSISTED DEVELOPMENT",
    title: "Building with AI",
    subtitle: "Using AI as a development assistant to understand, build, and improve the project.",
    image: "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=1600",
    heading: "How We Used AI",
    paragraphs: [
      "AI tools can help beginners understand programming concepts, plan system architecture, and identify possible coding errors.",
      "During development, AI can assist with ESP32 code, HTML and CSS design, JavaScript interactions, and Python data analysis.",
      "However, generated code must still be checked, tested, and modified to work correctly with the actual hardware."
    ],
    sideHeading: "Example AI Prompts",
    bullets: [
      "Explain how an ESP32 controls an OLED display.",
      "Help me create a medication reminder using millis().",
      "Design a responsive web dashboard using HTML and CSS.",
      "Write Python code to analyze medication records.",
      "Help me find errors in my code."
    ],
    fact: "AI is a development assistant, not a replacement for understanding, testing, and improving our own code."
  },

  {
    number: "05",
    kicker: "HARDWARE ARCHITECTURE",
    title: "Inside the SilverCare Box",
    subtitle: "The electronic components that make the physical reminder system work.",
    image: "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1600",
    heading: "Main Hardware Components",
    paragraphs: [
      "The ESP32 is the main controller of the system. It manages the reminder schedule, reads the button input, controls the buzzer, and communicates with the web dashboard.",
      "The OLED display provides a simple interface for showing medication information.",
      "A breadboard can be used to connect and test the electronic components during prototype development."
    ],
    sideHeading: "Pin Connections",
    code: `ESP32 COMPONENT CONNECTIONS

OLED SDA  → GPIO 21
OLED SCL  → GPIO 22
Buzzer    → GPIO 19
Button    → GPIO 23

Controller: ESP32
Display: OLED
Output: Buzzer
Input: Physical Button`,
    fact: "The ESP32 acts as the brain of SilverCare, connecting the input, output, and communication components."
  },

  {
    number: "06",
    kicker: "SYSTEM FLOW",
    title: "How the System Works",
    subtitle: "From the medication schedule to the final status record.",
    image: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1600",
    heading: "System Operation",
    paragraphs: [
      "The ESP32 checks the medication schedule continuously using a software clock and timing logic.",
      "When the scheduled time arrives, the buzzer sounds and the OLED displays the reminder.",
      "The user presses the TAKEN button after taking the medicine. The system records the confirmation and updates the medication status.",
      "If no confirmation is received within the allowed time, the system records the dose as MISSED."
    ],
    sideHeading: "System Flow",
    flow: [
      "Start System",
      "Check Schedule",
      "Reminder Time?",
      "Activate Buzzer",
      "User Confirms?",
      "Save Status"
    ],
    code: `SYSTEM LOGIC

1. Check current time
2. Compare with medicine schedule
3. If time matches:
   - Turn on buzzer
   - Display reminder
4. Wait for button input
5. If button pressed:
   - Save TAKEN
6. Otherwise:
   - Save MISSED`,
    fact: "The system follows a continuous checking process and records the user's response to each scheduled reminder."
  },

  {
    number: "07",
    kicker: "WEB DASHBOARD",
    title: "Medication Monitoring Dashboard",
    subtitle: "A simple web interface for checking medication status.",
    image: "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1600",
    heading: "Dashboard Features",
    paragraphs: [
      "The web dashboard provides a visual interface for monitoring the medication reminder system.",
      "The ESP32 can create its own Wi-Fi access point with the network name SilverCare-Box.",
      "After connecting to the device's Wi-Fi, a user can open the dashboard through the local address 192.168.4.1."
    ],
    sideHeading: "Dashboard Preview",
    status: true,
    code: `ESP32 WI-FI ACCESS

Network: SilverCare-Box
Local Address: 192.168.4.1

DASHBOARD STATUS

Morning Medicine    TAKEN
Afternoon Medicine  MISSED
Evening Medicine    PENDING`,
    fact: "The dashboard makes medication information easier to understand through a visual interface."
  },

  {
    number: "08",
    kicker: "PYTHON ANALYTICS",
    title: "Turning Records into Information",
    subtitle: "Python helps us understand medication habits through data analysis.",
    image: "https://images.unsplash.com/photo-1555949963-aa79dcee981c?w=1600",
    heading: "Why Python?",
    paragraphs: [
      "Medication events can be stored as structured data, such as JSON records containing the date, time, and medication status.",
      "Python can retrieve and process these records using libraries such as requests and pandas.",
      "Matplotlib can visualize the results in charts, making it easier to understand medication patterns over time."
    ],
    sideHeading: "Python Tools",
    bullets: [
      "requests — Communicate with a web service",
      "json — Read structured data",
      "pandas — Organize and analyze records",
      "matplotlib — Create charts and graphs",
      "dose_chart.png — Example chart output"
    ],
    code: `PYTHON ANALYTICS WORKFLOW

1. Receive medication records
2. Read JSON data
3. Process records with pandas
4. Calculate adherence rate
5. Visualize results
6. Save dose_chart.png`,
    fact: "Python transforms medication records into useful information that can help users understand their daily habits."
  },

  {
    number: "09",
    kicker: "RESULTS & DEMONSTRATION",
    title: "Testing the SilverCare System",
    subtitle: "A sample two-day simulation to demonstrate medication tracking.",
    image: "https://images.unsplash.com/photo-1559757175-0eb30cd8c063?w=1600",
    heading: "Example Test Results",
    paragraphs: [
      "The following example demonstrates how the system can record medication events during a two-day simulation.",
      "A total of five scheduled medication events were included. Four were confirmed as TAKEN, while one was recorded as MISSED.",
      "These sample results demonstrate how medication records can be summarized and visualized."
    ],
    sideHeading: "Simulation Statistics",
    stats: [
      ["4", "DOSES TAKEN"],
      ["1", "DOSES MISSED"],
      ["5", "TOTAL EVENTS"],
      ["80%", "ADHERENCE RATE"]
    ],
    status: true,
    bullets: [
      "Learned how to connect electronic components.",
      "Practiced ESP32 programming.",
      "Built a web-based interface.",
      "Used Python for data analysis.",
      "Understood the importance of testing hardware and software together."
    ],
    fact: "Example adherence rate = 4 confirmed doses ÷ 5 scheduled doses × 100 = 80%. These are simulation results, not clinical results."
  },

  {
    number: "10",
    kicker: "REFERENCES & PROJECT FILES",
    title: "Resources Behind the Project",
    subtitle: "The tools, technologies, and development resources used in SilverCare.",
    image: "https://images.unsplash.com/photo-1455390582262-044cdead277a?w=1600",
    heading: "Development Resources",
    paragraphs: [
      "SilverCare combines hardware development, embedded programming, web development, and data analysis.",
      "The project can be organized into separate folders for ESP32 firmware, dashboard files, Python analytics, and documentation."
    ],
    sideHeading: "Project Folder Structure",
    code: `SilverCare/
│
├── esp32/
│   └── silvercare.ino
│
├── dashboard/
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── python/
│   ├── analytics.py
│   └── dose_chart.png
│
└── README.md`,
    bullets: [
      "ESP32 documentation — docs.espressif.com",
      "Arduino documentation — docs.arduino.cc",
      "Python documentation — docs.python.org",
      "Pandas documentation — pandas.pydata.org",
      "Matplotlib documentation — matplotlib.org"
    ],
    fact: "SilverCare demonstrates how different areas of computer science and engineering can work together to solve a real-world problem."
  }
];


/* GET ELEMENTS */

const modal = document.getElementById("slideModal");
const slideContent = document.getElementById("slideContent");
const closeButton = document.getElementById("closeModal");
const backdrop = document.getElementById("modalBackdrop");
const previousButton = document.getElementById("prevSlide");
const nextButton = document.getElementById("nextSlide");
const currentNumber = document.getElementById("currentNumber");
const progressBar = document.getElementById("progressBar");

let currentSlide = 0;


/* BUILD SLIDE CONTENT */

function createSlideHTML(slide) {

  let leftContent = "";

  if (slide.paragraphs) {
    leftContent += slide.paragraphs
      .map(text => `<p>${text}</p>`)
      .join("");
  }

  if (slide.flow) {
    leftContent += `
      <div class="flow-list">
        ${slide.flow.map((step, index) => `
          <span class="flow-step">${step}</span>
          ${index !== slide.flow.length - 1
            ? '<span class="flow-arrow">→</span>'
            : ''}
        `).join("")}
      </div>
    `;
  }

  if (slide.stats) {
    leftContent += `
      <div class="stat-grid">
        ${slide.stats.map(stat => `
          <div class="stat-card">
            <strong>${stat[0]}</strong>
            <span>${stat[1]}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  let rightContent = "";

  if (slide.bullets) {
    rightContent += `
      <ul>
        ${slide.bullets.map(item => `<li>${item}</li>`).join("")}
      </ul>
    `;
  }

  if (slide.status) {
    rightContent += `
      <div class="status-list">
        <div class="status-row">
          Morning Medicine
          <span class="status-pill taken">TAKEN</span>
        </div>
        <div class="status-row">
          Afternoon Medicine
          <span class="status-pill missed">MISSED</span>
        </div>
        <div class="status-row">
          Evening Medicine
          <span class="status-pill pending">PENDING</span>
        </div>
      </div>
    `;
  }

  if (slide.code) {
    rightContent += `
      <div class="code-box">${slide.code}</div>
    `;
  }

  return `
    <div class="slide-hero"
      style="background-image: url('${slide.image}')">

      <div class="slide-hero-text">
        <div class="slide-kicker">${slide.kicker}</div>
        <h2>${slide.title}</h2>
        <p>${slide.subtitle}</p>
      </div>
    </div>

    <div class="slide-body">

      <section class="content-panel">
        <h3>${slide.heading}</h3>
        ${leftContent}
      </section>

      <section class="content-panel">
        <h3>${slide.sideHeading}</h3>
        ${rightContent}
      </section>

    </div>

    <div class="key-fact">
      <div class="key-icon">✦</div>
      <div>
        <strong>KEY FACT</strong>
        <p>${slide.fact}</p>
      </div>
    </div>
  `;
}


/* OPEN A SLIDE */

function openSlide(index) {

  currentSlide = index;

  const slide = slides[currentSlide];

  slideContent.innerHTML = createSlideHTML(slide);

  currentNumber.textContent = slide.number;

  progressBar.style.width =
    ((currentSlide + 1) / slides.length * 100) + "%";

  previousButton.disabled = currentSlide === 0;
  previousButton.style.opacity =
    currentSlide === 0 ? ".35" : "1";

  nextButton.textContent =
    currentSlide === slides.length - 1
      ? "Finish ✓"
      : "Next →";

  modal.classList.add("active");
  modal.setAttribute("aria-hidden", "false");

  document.body.style.overflow = "hidden";

  slideContent.scrollTop = 0;
}


/* CLOSE PRESENTATION */

function closeSlide() {

  modal.classList.remove("active");
  modal.setAttribute("aria-hidden", "true");

  document.body.style.overflow = "";
}


/* NEXT SLIDE */

function nextSlide() {

  if (currentSlide < slides.length - 1) {
    openSlide(currentSlide + 1);
  } else {
    closeSlide();
  }
}


/* PREVIOUS SLIDE */

function previousSlide() {

  if (currentSlide > 0) {
    openSlide(currentSlide - 1);
  }
}


/* CONNECT ALL 10 BUTTONS */

document.querySelectorAll(".slide-button").forEach(button => {

  button.addEventListener("click", () => {

    const index = Number(button.dataset.slide);

    openSlide(index);

  });

});


/* BUTTON EVENTS */

closeButton.addEventListener("click", closeSlide);

backdrop.addEventListener("click", closeSlide);

nextButton.addEventListener("click", nextSlide);

previousButton.addEventListener("click", previousSlide);


/* KEYBOARD NAVIGATION */

document.addEventListener("keydown", event => {

  if (!modal.classList.contains("active")) return;

  if (event.key === "Escape") {
    closeSlide();
  }

  if (event.key === "ArrowRight") {
    nextSlide();
  }

  if (event.key === "ArrowLeft") {
    previousSlide();
  }

});
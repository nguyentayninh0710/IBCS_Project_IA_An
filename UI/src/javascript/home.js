document.addEventListener("DOMContentLoaded", function(){
    const signup_btn = document.querySelector(".custom-signup");
    signup_btn.addEventListener("click", function(e){
        e.preventDefault();
        alert("Redirecting to sign-up");
    })
})

const pieChart = document.getElementById('pieChart').getContext('2d');
new Chart(pieChart, {
    type: 'pie',
    data: {
        lables: ['2 weeks before', 'Last week', 'This week'],
        datasets: [{
            lable: 'Current visits',
            data: [24.7, 18.3, 31.5, 25.5],
            backgroundColor:['rgb(201, 38, 38)','rgb(46, 230, 43)', 'rgb(27, 51, 208)', 'rgba(207, 172, 16, 0.96)' ]
        }]
    }
})

const baseOptions ={
  responsive: true,
  // maintainAspectRatio: false,
  plugins: {
    legend: {display: true, position: 'bottom'},
    tooltip: { enabled: true}
  },
  layout: { padding: 0 }
}

const lineChartEl = document.getElementById('lineChart');
if (lineChartEl) {
    new Chart(lineChartEl.getContext('2d'), {
        type: 'line',
        data: {
            labels: getLastSevenMonths(),
            datasets: [
                {
                    label: 'Team A',
                    data: getRandomNumber(),
                    borderColor: ' #ab2c50', 
                    backgroundColor: ' #54051b',
                    fill: true, 
                    tension: 0.35, 
                    pointRadius: 3
                },
                {
                    label: 'Team B',
                    data: getRandomNumber(),
                    borderColor: 'rgb(136, 77, 94)', 
                    backgroundColor: 'rgb(230, 34, 90)',
                    fill: true, 
                    tension: 0.35, 
                    pointRadius: 3
                },
            ]
        },
        options: {
            ...baseOptions,
            scales: {
                x: { grid: {display: false }},
                y: { beginAtZero: true }
            }
        }
    });
}

const barChart = document.getElementById('barChart')
if (barChart)
new Chart(barChart.getContext('2d'), {
    type: 'bar',
    data: {
        lables: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        datasets: [{
            lable: 'Current visits',
            data: [24.7, 18.3, 31.5, 25.5],
            backgroundColor:['rgb(201, 38, 38)','rgb(46, 230, 43)', 'rgb(27, 51, 208)', 'rgba(207, 172, 16, 0.96)' ]
        }]
    }
})

function getLastSevenMonths(){
    const lables = [];
    const now = new Date();
    for (let i = 6; i >= 0; i--){
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
        //2025-02-01
        lables.push(d.toLocaleString('en-US', { month: 'short'}));
    }
    console.log(Math.floor (Math.random));
    // random 0 -> 1
    Math.random()
    // Returns the greatest integer less than or equal to its numeric argument.
    Math.floor()
    return lables;
    console.log()
}

function getRandomNumber(){
    const random = [];
    for (let i = 0; i<=6; i++){
        random.push(Math.floor (Math.random() *200 ));
    }
   
    console.log (Math.floor(Math.random() *200 ));
    return random; 
}


//Create function to random 0 -> 200 and call this function in line chart






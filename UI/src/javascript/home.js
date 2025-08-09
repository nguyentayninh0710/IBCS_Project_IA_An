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
    //maintainAspectRatio: false,
    plugins: {
        legend: {display: true, position: 'bottom'},
        tooltip: { enable: true}
    },
    layout: { padding: 0}
}

const lineChart = document.getElementById('lineChart').getContext('2d');

if (lineChart){
    new Chart(lineChart, {
        type: 'line',
        data: {
            lables: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            datasets: [
                {
                    lable: 'Team A',
                    data: [15, 30, 45, 60, 75, 90],
                    borderColor: ' #ab2c50', 
                    backgroundColor: ' #54051b',
                    fill: true, 
                    tension: 0.35, 
                    pointRadius: 3
                },
                {
                    lable: 'Team B',
                    data: [20, 40, 60, 80, 100, 120],
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
                x: { grid: {display: flase}},
                y: { beginAtZero: true }
            }
        }
    }) 
}
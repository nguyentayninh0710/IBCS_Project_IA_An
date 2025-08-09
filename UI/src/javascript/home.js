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
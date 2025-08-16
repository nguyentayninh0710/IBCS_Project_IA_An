function login(){

}

function switchToSignup(){
    document.body.innerHTML = document.getElementByid('signupTemplate').innerHTML;
    initFormhandles();
} 

function initFormhandles(){
    const loginForm = document.getElementByid("loginForm");
    const signupForm = document.getElementByid("signupForm");

    if(loginForm){
        loginForm.addEventlistener("sumit", function (e){
            e.preventDefalt;
            login();
        }) 
    }
    if(signupForm){
        signupForm.addEventlistener("sumit", function (e){

        })
    }
}
window.onload = initFormHandlers;